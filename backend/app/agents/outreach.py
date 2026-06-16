"""Outreach agent — daily personalized email + SMS sequences.

Action: daily_sequences
  Input: {channel: "email" | "sms" | "both" (default both), max_leads: int = 10}
  Process:
    1. Find leads with next_followup_at <= now.
    2. For each, retrieve top-3 memories tagged `pattern` and any preferences.
    3. LLM (standard tier) drafts a personalized message conditioned on the memories.
    4. For email: save to email_drafts.
       For sms: queue via sms_tools (Twilio if configured, else mock).
    5. Update lead.last_contacted_at and reschedule next_followup_at in 4 days.
    6. Write outcome memory after.

Action: contact_lead  (one-off, called by the manager for ad-hoc outreach)
  Input: {lead_id: int, channel: "email" | "sms" (default "email")}
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import AsyncGenerator

from app.db.models import SessionLocal, Lead
from app.agents.base import Worker, WorkerSpec, WorkerEvent, route_llm, parse_json_lenient
from app.memory import store as memory
from app.tools import lead_pipeline, sms_tools, email_tools


SPEC = WorkerSpec(
    name="outreach",
    display_name="Outreach",
    description="Drafts personalized daily email + SMS sequences using shared-memory patterns.",
    actions=["daily_sequences", "contact_lead"],
    capabilities=(
        "daily_sequences(channel?, max_leads?): contact every lead due for follow-up. "
        "contact_lead(lead_id, channel?): contact one specific lead now."
    ),
)


def _retrieve_memory_block(company_id: int, lead: Lead, k: int = 4) -> str:
    """Pull patterns relevant to this lead, plus any company-wide preferences."""
    query = (
        f"How to write to a {lead.title or 'professional'} at a "
        f"{lead.industry or 'B2B'} company called {lead.company or 'theirs'}"
    )
    mems = memory.retrieve(
        company_id=company_id, query=query, k=k,
        kinds=("pattern", "preference", "win"),
        min_score=0.45,
    )
    if not mems:
        return "(no memory hits)"
    return "\n".join(f"- [{m.kind}] {m.content}" for m in mems)


async def _draft_for_lead(company_id: int, lead: Lead, channel: str,
                           memory_block: str, agent_name: str):
    """Generate an email or SMS for one lead. Returns (subject_or_none, body, router_info)."""
    if channel == "sms":
        system = (
            "You write very short B2B sales SMS messages. Hard rules: under 160 characters, "
            "personal, one clear ask, no 'I hope this email finds you well', no fluff. "
            "Use what's worked. Output: just the SMS body. No JSON, no quotes."
        )
    else:
        system = (
            "You write concise, personalized B2B cold emails. Under 120 words; one clear "
            "ask; reference the lead's notes; no fluff. Use what's worked. "
            "Output strictly JSON: "
            '{"subject":"...","body":"..."}. No markdown.'
        )

    user_prompt = (
        f"Lead: {lead.name}, {lead.title} at {lead.company} ({lead.industry}).\n"
        f"Notes: {lead.notes or '(none)'}\n"
        f"What's been working for similar leads:\n{memory_block}\n\n"
        f"Write the message."
    )
    result = await route_llm(system, user_prompt, tier="standard", agent_name=agent_name)

    router_info = {
        "model": result.model_used, "cost_usd": result.cost_usd,
        "cache_hit": result.was_cache_hit, "latency_ms": result.latency_ms,
    }

    if channel == "sms":
        body = result.content.strip()
        # Truncate to 160 chars
        if len(body) > 160:
            body = body[:157].rstrip() + "..."
        return None, body, router_info

    try:
        parsed = parse_json_lenient(result.content)
        return parsed.get("subject", "Quick question").strip(), parsed.get("body", "").strip(), router_info
    except Exception:
        return f"Quick question about {lead.company}", result.content.strip(), router_info


class OutreachWorker:
    spec = SPEC

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        company_id = int(input["company_id"])
        if action == "daily_sequences":
            async for ev in self._daily(company_id, input, task_id):
                yield ev
        elif action == "contact_lead":
            async for ev in self._contact(company_id, input, task_id):
                yield ev
        else:
            yield WorkerEvent("error", self.spec.name, f"Unknown action: {action}", task_id)

    async def _daily(self, company_id: int, input: dict, task_id: str):
        channel = input.get("channel", "both")
        max_leads = int(input.get("max_leads", 10))
        if channel not in ("email", "sms", "both"):
            yield WorkerEvent("error", self.spec.name, f"bad channel: {channel}", task_id)
            return

        due = lead_pipeline.leads_due_for_followup(company_id, limit=max_leads)
        if not due:
            yield WorkerEvent("done", self.spec.name,
                              {"contacted": 0, "note": "No leads due for follow-up"}, task_id)
            return

        yield WorkerEvent("tool", self.spec.name,
                          f"{len(due)} leads due for follow-up", task_id)

        results = []
        for lead in due:
            db = SessionLocal()
            try:
                memory_block = _retrieve_memory_block(company_id, lead, k=4)
            finally:
                db.close()

            channels = [channel] if channel != "both" else (
                ["email"] if not lead.email else ["email"]   # default to email; SMS only on demand
            )

            for ch in channels:
                subject, body, router_info = await _draft_for_lead(
                    company_id, lead, ch, memory_block, self.spec.name)

                if ch == "sms":
                    # Need a phone number — Phase 1 Lead model doesn't have one. Use a fake field.
                    phone = getattr(lead, "phone", None) or "+10000000000"
                    res = sms_tools.queue_sms(company_id=company_id, to_number=phone,
                                                body=body, lead_id=lead.id)
                    results.append({"lead_id": lead.id, "channel": "sms",
                                    "sms_id": res.get("sms_id"), "status": res.get("status"),
                                    "router": router_info})
                else:
                    db = SessionLocal()
                    try:
                        draft_id = email_tools.save_draft(db, company_id, lead.id, subject, body)
                    finally:
                        db.close()
                    results.append({"lead_id": lead.id, "channel": "email",
                                    "draft_id": draft_id, "subject": subject,
                                    "router": router_info})

            lead_pipeline.mark_contacted(company_id, lead.id)
            lead_pipeline.schedule_followup(company_id, lead.id, days=4)

        # Write a memory about today's outreach
        summary = (
            f"Contacted {len(due)} leads today: "
            f"{', '.join(set(r['channel'] for r in results))}. "
            f"Top patterns referenced from memory."
        )
        mem = await memory.compress_observation_to_memory(
            raw_observation=summary, agent_name=self.spec.name,
            context_hint=f"company_id={company_id}",
        )
        if mem.get("content"):
            memory.remember(
                company_id=company_id, kind=mem["kind"],
                content=mem["content"],
                tags=["outreach", "daily"] + mem.get("tags", []),
                source_agent=self.spec.name, importance=mem["importance"],
            )

        yield WorkerEvent("done", self.spec.name,
                          {"contacted": len(due), "results": results}, task_id)

    async def _contact(self, company_id: int, input: dict, task_id: str):
        lead_id = int(input["lead_id"])
        channel = input.get("channel", "email")
        db = SessionLocal()
        try:
            lead = db.query(Lead).filter(
                Lead.id == lead_id, Lead.company_id == company_id
            ).first()
        finally:
            db.close()
        if not lead:
            yield WorkerEvent("error", self.spec.name, f"lead {lead_id} not found", task_id)
            return

        memory_block = _retrieve_memory_block(company_id, lead)
        subject, body, router_info = await _draft_for_lead(
            company_id, lead, channel, memory_block, self.spec.name)

        if channel == "sms":
            phone = getattr(lead, "phone", None) or "+10000000000"
            res = sms_tools.queue_sms(company_id=company_id, to_number=phone,
                                        body=body, lead_id=lead_id)
            payload = {"channel": "sms", "lead_id": lead_id,
                       "sms_id": res.get("sms_id"), "status": res.get("status"),
                       "body": body, "router": router_info}
        else:
            db = SessionLocal()
            try:
                draft_id = email_tools.save_draft(db, company_id, lead_id, subject, body)
            finally:
                db.close()
            payload = {"channel": "email", "lead_id": lead_id, "draft_id": draft_id,
                       "subject": subject, "body": body, "router": router_info}

        lead_pipeline.mark_contacted(company_id, lead_id)
        yield WorkerEvent("done", self.spec.name, payload, task_id)
