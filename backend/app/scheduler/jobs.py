"""Job definitions.

Each job is a coroutine that runs an agent against a single company. The
runner loops over companies with scheduler_enabled=True and dispatches them.
"""
from __future__ import annotations
import logging
from datetime import datetime, date

from app.db.models import SessionLocal
from app.cost import tracing
from app.billing.context import scheduled_run
from app.agents.ceo import CEOWorker
from app.agents.insights import InsightsWorker
from app.agents.outreach import OutreachWorker
from app.agents.social_analyst import SocialAnalystWorker

log = logging.getLogger(__name__)


async def _run_agent(worker, action: str, input: dict, company_id: int,
                     job_name: str) -> dict:
    """Run a worker action with a trace context. Returns the 'done' payload or error."""
    ctx = tracing.TraceContext(
        company_id=company_id, session_id=None, parent_span_id=None,
        agent_name=worker.spec.name,
    )
    tracing.set_context(ctx)
    final = None
    err = None
    try:
        with scheduled_run():
            async for ev in worker.run(action, input, task_id=f"sched:{job_name}"):
                if ev.type == "done":
                    final = ev.content
                elif ev.type == "error":
                    err = ev.content
    except Exception as e:
        err = str(e)
    finally:
        tracing.set_context(None)
    return {"ok": err is None, "result": final, "error": err}


async def job_ceo_daily(company_id: int) -> dict:
    return await _run_agent(
        CEOWorker(), "daily_plan",
        {"company_id": company_id, "date": date.today().isoformat()},
        company_id, "ceo_daily",
    )


async def job_insights_daily(company_id: int) -> dict:
    return await _run_agent(
        InsightsWorker(), "extract_patterns",
        {"company_id": company_id, "lookback_days": 7},
        company_id, "insights_daily",
    )


async def job_outreach_daily(company_id: int) -> dict:
    return await _run_agent(
        OutreachWorker(), "daily_sequences",
        {"company_id": company_id, "channel": "email", "max_leads": 10},
        company_id, "outreach_daily",
    )


async def job_cmo_daily(company_id: int) -> dict:
    """Pull top competitor reels (handles configurable via memory), then script 3 new ones."""
    sa = SocialAnalystWorker()
    # Use whatever handles the company has stored as preferences in memory
    from app.memory import store as memory
    pref = memory.retrieve(company_id, "competitor handles to monitor", k=1,
                            kinds=("preference",), min_score=0.5)
    handles = ["competitor1", "competitor2"]  # fallback defaults
    if pref:
        # Try to parse handles out of the memory content
        try:
            import re
            text = pref[0].content
            found = re.findall(r"@?([a-zA-Z0-9_.]+)", text)
            if found:
                handles = found[:5]
        except Exception:
            pass

    # Step 1: pull competitor reels (no-op if Apify not configured + table empty)
    await _run_agent(sa, "competitor_reels",
                      {"company_id": company_id, "handles": handles,
                       "platform": "instagram"},
                      company_id, "cmo_daily_reels")
    # Step 2: script 3 new reels
    return await _run_agent(sa, "script_reels",
                             {"company_id": company_id, "count": 3},
                             company_id, "cmo_daily_scripts")


JOB_REGISTRY = {
    "ceo_daily": job_ceo_daily,
    "insights_daily": job_insights_daily,
    "outreach_daily": job_outreach_daily,
    "cmo_daily": job_cmo_daily,
}


DEFAULT_CRONS = {
    "ceo_daily":      "0 6 * * *",   # 06:00 UTC
    "cmo_daily":      "0 7 * * *",   # 07:00 UTC
    "insights_daily": "30 7 * * *",  # 07:30 UTC
    "outreach_daily": "0 9 * * *",   # 09:00 UTC
}
