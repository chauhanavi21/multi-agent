"""Sales agent — Phase 6.

Existing actions (Phase 4): draft_email, generate_leads, search_leads.
New actions (Phase 6):
  - qualify_lead(lead_id): scores against the company's ICP profile (LLM)
  - transition_stage(lead_id, to_stage, reason?): explicit stage move
  - follow_up_now(lead_id, channel?): kick the outreach agent on demand

Every new action that produces a meaningful outcome writes a memory.
"""
from __future__ import annotations
import json
from typing import AsyncGenerator

from app.db.models import SessionLocal, Lead
from app.tools import lead_tools, email_tools, lead_pipeline
from app.agents.base import (
    Worker, WorkerSpec, WorkerEvent, route_llm, parse_json_lenient,
)
from app.memory import store as memory
from app.billing.plans import get_company_plan, resolve_sales_tier


ACTION_TIERS = {
    "draft_email": "standard",
    "generate_leads": "standard",
    "search_leads": "cheap",
    "qualify_lead": "cheap",
    "transition_stage": "cheap",
    "follow_up_now": "standard",
}


SPEC = WorkerSpec(
    name="sales",
    display_name="Sales / Lead pipeline",
    description="Manages leads, drafts cold emails, qualifies against ICP, transitions stages.",
    actions=list(ACTION_TIERS.keys()),
    capabilities=(
        "draft_email(lead_id): personalized cold email draft. "
        "generate_leads(criteria): create 3 fictional realistic leads. "
        "search_leads(criteria): filter existing leads. "
        "qualify_lead(lead_id): score against ICP and transition to 'qualified' if >=70. "
        "transition_stage(lead_id, to_stage, reason?): explicit stage move with history. "
        "follow_up_now(lead_id, channel?): trigger immediate outreach."
    ),
)


def _require_company(input: dict, agent_name: str, task_id: str):
    cid = input.get("company_id")
    if not cid:
        return None, WorkerEvent("error", agent_name, "Missing company_id", task_id)
    return int(cid), None


class SalesWorker:
    spec = SPEC

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        handlers = {
            "draft_email": self._draft_email,
            "generate_leads": self._generate_leads,
            "search_leads": self._search_leads,
            "qualify_lead": self._qualify_lead,
            "transition_stage": self._transition_stage,
            "follow_up_now": self._follow_up_now,
        }
        h = handlers.get(action)
        if not h:
            yield WorkerEvent("error", self.spec.name, f"Unknown action: {action}", task_id)
            return
        async for ev in h(input, task_id):
            yield ev

    async def _draft_email(self, input, task_id):
        company_id, err = _require_company(input, self.spec.name, task_id)
        if err: yield err; return
        lead_id = input.get("lead_id")
        if not lead_id:
            yield WorkerEvent("error", self.spec.name, "lead_id required", task_id); return

        db = SessionLocal()
        try:
            lead = lead_tools.get_lead(db, company_id, int(lead_id))
            if not lead:
                yield WorkerEvent("error", self.spec.name,
                                  f"Lead {lead_id} not found", task_id); return

            # Memory retrieval — what's worked for similar leads
            query = f"{lead['title']} at {lead['industry']} company {lead['company']}"
            mems = memory.retrieve(company_id, query, k=4,
                                   kinds=("pattern", "win", "preference"))
            memory_block = "\n".join(f"- {m.content}" for m in mems) or "(none)"

            yield WorkerEvent("tool", self.spec.name,
                              f"Drafting; using {len(mems)} relevant memories", task_id)

            system = (
                "You write concise, personalized B2B cold emails. Under 120 words, one clear "
                "ask, no fluff. Use what's worked. "
                'Output strictly JSON: {"subject":"...","body":"..."}.'
            )
            user = (
                f"Lead: {lead['name']}, {lead['title']} at {lead['company']} "
                f"({lead['industry']}).\nNotes: {lead['notes']}\n"
                f"What's worked recently:\n{memory_block}\n"
                f"Write the email."
            )
            plan = get_company_plan(db, company_id)
            draft_tier = resolve_sales_tier(plan, "draft_email")
            result = await route_llm(system, user, tier=draft_tier,
                                     agent_name=self.spec.name)

            try:
                parsed = parse_json_lenient(result.content)
            except Exception:
                parsed = {"subject": f"Quick question about {lead['company']}",
                          "body": result.content.strip()}

            draft_id = email_tools.save_draft(db, company_id, lead["id"],
                                              parsed["subject"], parsed["body"])
            if draft_id is None:
                yield WorkerEvent("error", self.spec.name, "Failed to save draft", task_id); return

            yield WorkerEvent("done", self.spec.name,
                              {"draft_id": draft_id, "lead_id": lead["id"],
                               "lead_name": lead["name"],
                               "subject": parsed["subject"], "body": parsed["body"],
                               "memories_used": len(mems),
                               "_router": {"model": result.model_used,
                                           "cost_usd": result.cost_usd,
                                           "cache_hit": result.was_cache_hit,
                                           "latency_ms": result.latency_ms}},
                              task_id)
        finally:
            db.close()

    async def _generate_leads(self, input, task_id):
        company_id, err = _require_company(input, self.spec.name, task_id)
        if err: yield err; return
        criteria = input.get("criteria", "B2B SaaS companies")
        yield WorkerEvent("tool", self.spec.name,
                          f"Generating 3 leads for: {criteria}", task_id)
        system = (
            "Generate exactly 3 fictional but realistic B2B leads. "
            "Output strictly a JSON array: "
            '[{"name":"","title":"","company":"","industry":"","email":"","notes":""}]. '
            "Emails use .example domain. No markdown."
        )
        result = await route_llm(system, f"Criteria: {criteria}",
                                 tier=ACTION_TIERS["generate_leads"],
                                 agent_name=self.spec.name)
        try:
            arr = parse_json_lenient(result.content)
        except Exception:
            yield WorkerEvent("error", self.spec.name, "LLM returned non-JSON", task_id); return
        if not isinstance(arr, list) or not arr:
            yield WorkerEvent("error", self.spec.name,
                              "LLM did not return a non-empty list", task_id); return

        created = []
        db = SessionLocal()
        try:
            for row in arr[:3]:
                try:
                    nid = lead_tools.add_lead(db, company_id, row)
                    created.append({**row, "id": nid})
                except Exception as e:
                    db.rollback()
                    yield WorkerEvent("tool", self.spec.name, f"Skipped: {e}", task_id)
        finally:
            db.close()

        yield WorkerEvent("done", self.spec.name, {"created": created}, task_id)

    async def _search_leads(self, input, task_id):
        company_id, err = _require_company(input, self.spec.name, task_id)
        if err: yield err; return
        criteria = input.get("criteria")
        db = SessionLocal()
        try:
            results = lead_tools.search_leads(db, company_id, criteria=criteria, limit=20)
        finally:
            db.close()
        yield WorkerEvent("done", self.spec.name, {"leads": results}, task_id)

    async def _qualify_lead(self, input, task_id):
        from app.db.migrate_phase3 import Company
        company_id, err = _require_company(input, self.spec.name, task_id)
        if err: yield err; return
        lead_id = int(input.get("lead_id", 0))
        if not lead_id:
            yield WorkerEvent("error", self.spec.name, "lead_id required", task_id); return

        db = SessionLocal()
        try:
            company = db.query(Company).filter(Company.id == company_id).first()
            icp = getattr(company, "icp_profile", None) or ""
            lead = lead_tools.get_lead(db, company_id, lead_id)
            if not lead:
                yield WorkerEvent("error", self.spec.name,
                                  f"Lead {lead_id} not found", task_id); return
        finally:
            db.close()

        if not icp.strip():
            yield WorkerEvent("tool", self.spec.name,
                              "Company has no ICP profile set — using default heuristic.",
                              task_id)
            icp = "Mid-market B2B SaaS, ICP score 50 unless lead is clearly senior decision-maker."

        system = (
            "You score B2B leads against an ICP profile. Output strictly JSON: "
            '{"score":0-100,"rationale":"<one sentence>","tags":["..."]}. '
            "Be honest, no inflation. 70+ means high-fit; below 50 means weak fit."
        )
        user = f"ICP profile:\n{icp}\n\nLead:\n{json.dumps(lead, default=str)}"
        result = await route_llm(system, user, tier=ACTION_TIERS["qualify_lead"],
                                  agent_name=self.spec.name)
        try:
            parsed = parse_json_lenient(result.content)
            score = int(parsed.get("score", 0))
            rationale = parsed.get("rationale", "")
        except Exception:
            score = 50
            rationale = result.content.strip()[:200]

        lead_pipeline.set_icp_score(company_id, lead_id, score, rationale=rationale)

        transitioned = False
        if score >= 70:
            lead_pipeline.transition(company_id, lead_id, "qualified",
                                      reason=rationale, agent=self.spec.name)
            transitioned = True

        # Write a memory about the qualification
        memory.remember(
            company_id=company_id, kind="fact",
            content=(f"Lead {lead['name']} ({lead['title']} at {lead['company']}, "
                     f"{lead['industry']}) scored {score}/100. Reason: {rationale}"),
            tags=["icp", "qualification", lead['industry'] or "unknown"],
            source_agent=self.spec.name, importance=0.5,
        )

        yield WorkerEvent("done", self.spec.name,
                          {"lead_id": lead_id, "score": score, "rationale": rationale,
                           "transitioned_to_qualified": transitioned,
                           "_router": {"model": result.model_used,
                                       "cost_usd": result.cost_usd,
                                       "cache_hit": result.was_cache_hit}},
                          task_id)

    async def _transition_stage(self, input, task_id):
        company_id, err = _require_company(input, self.spec.name, task_id)
        if err: yield err; return
        lead_id = int(input.get("lead_id", 0))
        to_stage = input.get("to_stage")
        reason = input.get("reason")
        res = lead_pipeline.transition(company_id, lead_id, to_stage,
                                         reason=reason, agent=self.spec.name)
        if not res["ok"]:
            yield WorkerEvent("error", self.spec.name, res.get("error", "failed"), task_id)
            return
        # Memory if it's a win or loss
        if to_stage in ("won", "lost"):
            memory.remember(
                company_id=company_id,
                kind="win" if to_stage == "won" else "loss",
                content=f"Lead {lead_id} moved to {to_stage}. Reason: {reason or 'unspecified'}",
                tags=[to_stage, "outcome"],
                source_agent=self.spec.name, outcome=to_stage, importance=0.8,
            )
        yield WorkerEvent("done", self.spec.name, res, task_id)

    async def _follow_up_now(self, input, task_id):
        """Delegates to the outreach worker for one specific lead."""
        from app.agents.outreach import OutreachWorker
        outreach = OutreachWorker()
        async for ev in outreach.run("contact_lead", input, task_id):
            yield ev


# ---- backward-compat with Phase 1 endpoints ----
import asyncio


def run_agent(task: str, company_id: int, lead_id: int | None = None,
              criteria: str | None = None):
    worker = SalesWorker()
    inp = {"company_id": company_id}
    if lead_id is not None: inp["lead_id"] = lead_id
    if criteria is not None: inp["criteria"] = criteria

    async def collect():
        out = []
        async for ev in worker.run(task, inp, task_id="legacy"):
            if ev.type == "done":
                if task == "draft_email" and isinstance(ev.content, dict):
                    out.append({"type": "draft_ready", "content": ev.content})
                elif task == "generate_leads" and isinstance(ev.content, dict):
                    out.append({"type": "leads_created",
                                "content": ev.content.get("created", [])})
                out.append({"type": "done", "content": ev.content})
            else:
                out.append({"type": ev.type, "content": ev.content})
        return out

    for ev in asyncio.run(collect()):
        yield ev
