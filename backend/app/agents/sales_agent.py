"""Sales agent — Phase 3: company-scoped.

The Worker.run signature is unchanged, but `input` now carries `company_id`.
The manager injects it before calling any worker.
"""
from __future__ import annotations
import json
import asyncio
from typing import AsyncGenerator
from langchain_core.messages import HumanMessage, SystemMessage

from app.db.models import SessionLocal
from app.tools import lead_tools, email_tools
from app.agents.base import (
    Worker, WorkerSpec, WorkerEvent, get_llm, parse_json_lenient,
)


SPEC = WorkerSpec(
    name="sales",
    display_name="Sales agent",
    description="Manages leads, drafts cold emails, generates new leads.",
    actions=["draft_email", "generate_leads", "search_leads"],
    capabilities=(
        "draft_email(lead_id): write a personalized cold email and save as draft. "
        "generate_leads(criteria): create 3 fictional but realistic leads. "
        "search_leads(criteria): filter existing leads by industry/title/company."
    ),
)


def _require_company(input: dict, agent_name: str, task_id: str):
    cid = input.get("company_id")
    if not cid:
        return None, WorkerEvent("error", agent_name, "Missing company_id in worker input", task_id)
    return int(cid), None


class SalesWorker:
    spec = SPEC

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        if action == "draft_email":
            async for ev in self._draft_email(input, task_id):
                yield ev
        elif action == "generate_leads":
            async for ev in self._generate_leads(input, task_id):
                yield ev
        elif action == "search_leads":
            async for ev in self._search_leads(input, task_id):
                yield ev
        else:
            yield WorkerEvent("error", self.spec.name, f"Unknown action: {action}", task_id)

    async def _draft_email(self, input: dict, task_id: str):
        company_id, err = _require_company(input, self.spec.name, task_id)
        if err:
            yield err
            return

        lead_id = input.get("lead_id")
        if not lead_id:
            yield WorkerEvent("error", self.spec.name, "lead_id required", task_id)
            return

        db = SessionLocal()
        try:
            lead = lead_tools.get_lead(db, company_id, int(lead_id))
            if not lead:
                yield WorkerEvent("error", self.spec.name,
                                  f"Lead {lead_id} not found in this company", task_id)
                return

            yield WorkerEvent("tool", self.spec.name,
                              f"Loaded lead: {lead['name']} ({lead['company']})", task_id)
            yield WorkerEvent("thinking", self.spec.name, "Drafting email...", task_id)

            system = (
                "You write concise, personalized B2B cold emails. "
                "Rules: under 120 words; one clear ask; reference the lead's notes; "
                "no fluff, no 'I hope this email finds you well'. "
                "Output strictly as JSON: {\"subject\": \"...\", \"body\": \"...\"}. "
                "No markdown, no code fences, just the raw JSON object."
            )
            user = (
                f"Lead: {lead['name']}, {lead['title']} at {lead['company']} "
                f"({lead['industry']}).\nNotes: {lead['notes']}\n"
                f"We sell a developer-focused agent platform that automates outbound + ops. "
                f"Write the email."
            )
            llm = get_llm()
            resp = await asyncio.to_thread(
                llm.invoke, [SystemMessage(content=system), HumanMessage(content=user)]
            )
            try:
                parsed = parse_json_lenient(resp.content)
            except Exception:
                parsed = {
                    "subject": f"Quick question about {lead['company']}",
                    "body": resp.content.strip(),
                }
            draft_id = email_tools.save_draft(db, company_id, lead["id"],
                                              parsed["subject"], parsed["body"])
            if draft_id is None:
                yield WorkerEvent("error", self.spec.name, "Failed to save draft", task_id)
                return
            payload = {
                "draft_id": draft_id, "lead_id": lead["id"],
                "lead_name": lead["name"],
                "subject": parsed["subject"], "body": parsed["body"],
            }
            yield WorkerEvent("done", self.spec.name, payload, task_id)
        finally:
            db.close()

    async def _generate_leads(self, input: dict, task_id: str):
        company_id, err = _require_company(input, self.spec.name, task_id)
        if err:
            yield err
            return

        criteria = input.get("criteria", "B2B SaaS companies")
        db = SessionLocal()
        try:
            yield WorkerEvent("tool", self.spec.name,
                              f"Generating 3 leads for: {criteria}", task_id)
            system = (
                "Generate exactly 3 fictional but realistic B2B leads. "
                "Output strictly a JSON array: "
                "[{\"name\":\"\",\"title\":\"\",\"company\":\"\",\"industry\":\"\",\"email\":\"\",\"notes\":\"\"}]. "
                "Emails must use the .example domain. No markdown, no code fences."
            )
            llm = get_llm()
            resp = await asyncio.to_thread(
                llm.invoke,
                [SystemMessage(content=system), HumanMessage(content=f"Criteria: {criteria}")],
            )
            try:
                arr = parse_json_lenient(resp.content)
            except Exception:
                yield WorkerEvent("error", self.spec.name, "LLM returned non-JSON", task_id)
                return
            if not isinstance(arr, list):
                yield WorkerEvent("error", self.spec.name,
                                  f"LLM did not return a JSON array (got {type(arr).__name__})", task_id)
                return
            if not arr:
                yield WorkerEvent("error", self.spec.name,
                                  "LLM returned an empty list — try more specific criteria", task_id)
                return

            created = []
            for row in arr[:3]:
                try:
                    nid = lead_tools.add_lead(db, company_id, row)
                    created.append({**row, "id": nid})
                except Exception as e:
                    db.rollback()
                    yield WorkerEvent("tool", self.spec.name,
                                      f"Skipped (dup or bad row): {e}", task_id)

            yield WorkerEvent("done", self.spec.name, {"created": created}, task_id)
        finally:
            db.close()

    async def _search_leads(self, input: dict, task_id: str):
        company_id, err = _require_company(input, self.spec.name, task_id)
        if err:
            yield err
            return

        criteria = input.get("criteria")
        db = SessionLocal()
        try:
            results = lead_tools.search_leads(db, company_id, criteria=criteria, limit=20)
            yield WorkerEvent("tool", self.spec.name,
                              f"Found {len(results)} leads matching '{criteria}'", task_id)
            yield WorkerEvent("done", self.spec.name, {"leads": results}, task_id)
        finally:
            db.close()


# ---- backward compat with Phase 1 endpoints ----

def run_agent(task: str, company_id: int, lead_id: int | None = None,
              criteria: str | None = None):
    """Sync generator wrapper used by the original Phase 1 SSE endpoints (now company-scoped)."""
    worker = SalesWorker()
    inp = {"company_id": company_id}
    if lead_id is not None:
        inp["lead_id"] = lead_id
    if criteria is not None:
        inp["criteria"] = criteria

    async def collect():
        out = []
        async for ev in worker.run(task, inp, task_id="legacy"):
            if ev.type == "done":
                if task == "draft_email" and isinstance(ev.content, dict):
                    out.append({"type": "draft_ready", "content": ev.content})
                elif task == "generate_leads" and isinstance(ev.content, dict):
                    out.append({"type": "leads_created", "content": ev.content.get("created", [])})
                out.append({"type": "done", "content": ev.content})
            else:
                out.append({"type": ev.type, "content": ev.content})
        return out

    events = asyncio.run(collect())
    for ev in events:
        yield ev
