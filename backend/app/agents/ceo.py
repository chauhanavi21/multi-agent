"""CEO agent — the daily planner.

Action: daily_plan
  Input: {date: "YYYY-MM-DD"}   (defaults to today)
  Process:
    1. Pulls yesterday's task completions, lead stage changes, sent drafts.
    2. Retrieves memories from the last 7 days (lessons, patterns, wins, losses).
    3. LLM (quality tier) writes a narrative summary + 3-7 priorities for today.
    4. Stores result in daily_plans.
    5. Writes a memory: "yesterday focused on X; today focuses on Y".
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta, date
from typing import AsyncGenerator

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import SessionLocal, Lead
from app.agents.base import Worker, WorkerSpec, WorkerEvent, route_llm, parse_json_lenient
from app.memory import store as memory


SPEC = WorkerSpec(
    name="ceo",
    display_name="CEO",
    description="Reviews yesterday and writes today's priorities; updates the daily plan.",
    actions=["daily_plan", "status_report"],
    capabilities=(
        "daily_plan(date?): produce today's plan with priorities and metrics summary. "
        "status_report(): one-paragraph state of the business right now."
    ),
)


def _yesterdays_metrics(db: Session, company_id: int) -> dict:
    """Roll up what happened in the last ~24h."""
    from app.db.migrate_phase4 import UsageRecord
    from app.db.migrate_phase6 import LeadStageHistory, DailyPlan
    since = datetime.utcnow() - timedelta(days=1)

    leads_added = db.query(func.count(Lead.id)).filter(
        Lead.company_id == company_id, Lead.created_at >= since
    ).scalar() or 0

    stage_changes = db.query(func.count(LeadStageHistory.id)).filter(
        LeadStageHistory.company_id == company_id,
        LeadStageHistory.created_at >= since,
    ).scalar() or 0

    cost_yesterday = db.query(func.coalesce(func.sum(UsageRecord.cost_usd), 0)).filter(
        UsageRecord.company_id == company_id,
        UsageRecord.created_at >= since,
    ).scalar() or 0.0

    # Latest stage breakdown (snapshot)
    stage_counts_rows = db.query(
        Lead.current_stage, func.count(Lead.id)
    ).filter(
        Lead.company_id == company_id
    ).group_by(Lead.current_stage).all()

    return {
        "lookback_hours": 24,
        "leads_added": int(leads_added),
        "stage_changes": int(stage_changes),
        "cost_usd": round(float(cost_yesterday), 6),
        "stage_counts": {(s or "unset"): int(n) for s, n in stage_counts_rows},
    }


class CEOWorker:
    spec = SPEC

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        company_id = int(input["company_id"])
        if action == "daily_plan":
            async for ev in self._daily_plan(company_id, input, task_id):
                yield ev
        elif action == "status_report":
            async for ev in self._status_report(company_id, task_id):
                yield ev
        else:
            yield WorkerEvent("error", self.spec.name, f"Unknown action: {action}", task_id)

    async def _daily_plan(self, company_id: int, input: dict, task_id: str):
        from app.db.migrate_phase6 import DailyPlan
        from app.db.migrate_phase3 import Company

        plan_date = input.get("date") or date.today().isoformat()
        yield WorkerEvent("thinking", self.spec.name, f"Compiling plan for {plan_date}", task_id)

        db = SessionLocal()
        try:
            company = db.query(Company).filter(Company.id == company_id).first()
            icp = getattr(company, "icp_profile", None) or "(not set)"
            metrics = _yesterdays_metrics(db, company_id)
        finally:
            db.close()

        yield WorkerEvent("tool", self.spec.name,
                          f"Yesterday: {metrics['leads_added']} new leads, "
                          f"{metrics['stage_changes']} stage changes, "
                          f"${metrics['cost_usd']:.4f} spent",
                          task_id)

        # Retrieve recent strategic memories
        relevant = memory.retrieve(
            company_id,
            query="weekly priorities, patterns that worked, what to do next",
            k=8,
            kinds=("lesson", "pattern", "win", "loss"),
            min_score=0.45,
        )
        memory_block = "\n".join(f"- [{m.kind}] {m.content}" for m in relevant) or "(none)"

        system = (
            "You are the CEO of a small B2B company. Your job each morning is to write a SHORT "
            "narrative review of yesterday and propose 3-7 concrete priorities for today. "
            "Be specific. Reference numbers. Prioritize ruthlessly. "
            "Output strictly JSON:\n"
            '{"summary":"<2-4 sentences>","priorities":["...","..."]}'
        )
        user_prompt = (
            f"Plan date: {plan_date}\n"
            f"ICP: {icp}\n"
            f"Yesterday's metrics: {json.dumps(metrics)}\n"
            f"Relevant memories:\n{memory_block}\n\n"
            f"Write the plan."
        )

        result = await route_llm(system, user_prompt, tier="quality",
                                  agent_name=self.spec.name)
        try:
            plan = parse_json_lenient(result.content)
        except Exception:
            plan = {"summary": result.content[:600], "priorities": []}

        # Persist
        db = SessionLocal()
        try:
            existing = db.query(DailyPlan).filter(
                DailyPlan.company_id == company_id,
                DailyPlan.plan_date == plan_date,
            ).first()
            if existing:
                existing.summary = plan.get("summary", "")[:2000]
                existing.priorities = plan.get("priorities", [])[:10]
                existing.metrics_yesterday = metrics
            else:
                row = DailyPlan(
                    company_id=company_id, plan_date=plan_date,
                    summary=plan.get("summary", "")[:2000],
                    priorities=plan.get("priorities", [])[:10],
                    metrics_yesterday=metrics,
                )
                db.add(row)
            db.commit()
        finally:
            db.close()

        # Write a memory for future CEO runs to learn from
        if plan.get("summary"):
            mem = await memory.compress_observation_to_memory(
                raw_observation=f"On {plan_date}, the daily plan was: {plan.get('summary')}. "
                                f"Priorities: {', '.join(plan.get('priorities', [])[:5])}. "
                                f"Yesterday's metrics: {json.dumps(metrics)}.",
                agent_name=self.spec.name,
                context_hint=f"company_id={company_id}",
            )
            if mem.get("content"):
                memory.remember(
                    company_id=company_id, kind=mem["kind"],
                    content=mem["content"], tags=["daily_plan", "ceo"] + mem.get("tags", []),
                    source_agent=self.spec.name, importance=mem["importance"],
                )

        yield WorkerEvent("done", self.spec.name,
                          {"plan_date": plan_date,
                           "summary": plan.get("summary"),
                           "priorities": plan.get("priorities", []),
                           "metrics_yesterday": metrics,
                           "_router": {"model": result.model_used,
                                       "cost_usd": result.cost_usd,
                                       "cache_hit": result.was_cache_hit}},
                          task_id)

    async def _status_report(self, company_id: int, task_id: str):
        db = SessionLocal()
        try:
            metrics = _yesterdays_metrics(db, company_id)
        finally:
            db.close()
        yield WorkerEvent("done", self.spec.name,
                          {"metrics": metrics,
                           "summary": f"{metrics['leads_added']} new leads in 24h, "
                                      f"{metrics['stage_changes']} stage changes, "
                                      f"${metrics['cost_usd']:.4f} spent"},
                          task_id)
