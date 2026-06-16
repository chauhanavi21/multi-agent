"""Insights agent — pattern miner.

Action: extract_patterns
  Input: {lookback_days: int = 7}
  Process:
    1. Pulls leads that moved from contacted -> qualified or qualified -> won in window.
    2. Pulls the drafts that were sent to those leads.
    3. LLM (standard tier) is asked to identify 3-5 patterns in the converting messages.
    4. Each pattern is written as a memory (kind=pattern, tags=[outreach, ...]).
    5. Returns the patterns as a summary.

The outreach agent retrieves memories where kind=pattern at run time, so this
is the closed loop: insights -> memory -> better outreach.
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from typing import AsyncGenerator

from sqlalchemy import select

from app.db.models import SessionLocal, Lead, EmailDraft
from app.agents.base import Worker, WorkerSpec, WorkerEvent, route_llm, parse_json_lenient
from app.memory import store as memory


SPEC = WorkerSpec(
    name="insights",
    display_name="Insights",
    description="Mines what's actually converting and writes patterns into shared memory.",
    actions=["extract_patterns"],
    capabilities=(
        "extract_patterns(lookback_days?): find what worked in the last N days "
        "and write reusable patterns into memory."
    ),
)


def _gather_winning_data(db, company_id: int, lookback_days: int):
    """Return a compact dataset of (lead snapshot, drafts) for recently-progressing leads."""
    from app.db.migrate_phase6 import LeadStageHistory
    since = datetime.utcnow() - timedelta(days=lookback_days)

    # Find recently progressed leads (qualified or won)
    progressed = db.query(LeadStageHistory).filter(
        LeadStageHistory.company_id == company_id,
        LeadStageHistory.created_at >= since,
        LeadStageHistory.to_stage.in_(("qualified", "in_conversation", "won")),
    ).all()

    by_lead = {}
    for h in progressed:
        by_lead.setdefault(h.lead_id, []).append({
            "from": h.from_stage, "to": h.to_stage,
            "at": h.created_at.isoformat() if h.created_at else None,
        })

    out = []
    for lead_id, history in list(by_lead.items())[:30]:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.company_id == company_id).first()
        if not lead:
            continue
        drafts = db.query(EmailDraft).filter(
            EmailDraft.lead_id == lead_id, EmailDraft.company_id == company_id
        ).order_by(EmailDraft.id).all()
        out.append({
            "lead": {
                "industry": lead.industry, "title": lead.title,
                "company": lead.company, "icp_score": getattr(lead, "icp_score", None),
                "notes": (lead.notes or "")[:200],
            },
            "stage_history": history,
            "drafts": [
                {"subject": d.subject, "body": (d.body or "")[:400], "sent": d.sent}
                for d in drafts
            ][:3],
        })
    return out


class InsightsWorker:
    spec = SPEC

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        if action != "extract_patterns":
            yield WorkerEvent("error", self.spec.name, f"Unknown action: {action}", task_id)
            return

        company_id = int(input["company_id"])
        lookback = int(input.get("lookback_days", 7))
        yield WorkerEvent("tool", self.spec.name,
                          f"Scanning last {lookback}d for converting patterns", task_id)

        db = SessionLocal()
        try:
            dataset = _gather_winning_data(db, company_id, lookback)
        finally:
            db.close()

        if not dataset:
            yield WorkerEvent("done", self.spec.name,
                              {"patterns_found": 0,
                               "summary": "No qualifying activity in the window — write more "
                                          "before insights can mine anything.",
                               "lookback_days": lookback},
                              task_id)
            return

        yield WorkerEvent("tool", self.spec.name,
                          f"Analyzing {len(dataset)} progressing leads", task_id)

        system = (
            "You are a sales/marketing analyst. Given a dataset of leads that progressed in "
            "the funnel and the messages we sent them, identify 3-5 distinct patterns that "
            "appear to be working. Each pattern must be: specific (mentions industries / roles "
            "/ language), actionable (others can copy it), and one short sentence. "
            "Output JSON: "
            '{"patterns":[{"content":"...","tags":["..."],"importance":0.0-1.0}], '
            '"summary":"<one paragraph for the human>"}'
        )
        user_prompt = (
            f"Dataset ({len(dataset)} leads):\n{json.dumps(dataset, default=str)[:8000]}\n\n"
            f"Find patterns."
        )

        result = await route_llm(system, user_prompt, tier="standard",
                                  agent_name=self.spec.name)
        try:
            parsed = parse_json_lenient(result.content)
            patterns = parsed.get("patterns", []) or []
            summary = parsed.get("summary", "")
        except Exception:
            patterns = []
            summary = result.content[:600]

        # Write patterns into memory
        written = []
        for p in patterns[:5]:
            content = (p.get("content") or "").strip()
            if not content:
                continue
            mid = memory.remember(
                company_id=company_id, kind="pattern",
                content=content,
                tags=["outreach", "conversion"] + [str(t)[:30] for t in (p.get("tags") or [])][:3],
                source_agent=self.spec.name,
                importance=float(p.get("importance", 0.7)),
            )
            if mid is not None:
                written.append(mid)

        yield WorkerEvent("done", self.spec.name,
                          {"patterns_found": len(written),
                           "memory_ids": written,
                           "summary": summary[:1000],
                           "_router": {"model": result.model_used,
                                       "cost_usd": result.cost_usd,
                                       "cache_hit": result.was_cache_hit}},
                          task_id)
