"""Observability routes — traces, cost dashboards, cache stats."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.auth.deps import get_company_context, CompanyContext
from app.cost import tracing, cache, budget
from app.billing.plans import get_company_plan, plan_summary


router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/traces/recent")
def recent_traces(limit: int = 100,
                  ctx: CompanyContext = Depends(get_company_context),
                  db: Session = Depends(get_db)):
    """Most recent traces for this company."""
    return tracing.list_spans_for_company(db, ctx.company_id, limit=min(limit, 500))


@router.get("/traces/session/{session_id}")
def session_traces(session_id: int,
                   ctx: CompanyContext = Depends(get_company_context),
                   db: Session = Depends(get_db)):
    """All spans for a specific chat session."""
    return tracing.list_spans_for_session(db, session_id, ctx.company_id)


@router.get("/cost/summary")
def cost_summary(ctx: CompanyContext = Depends(get_company_context),
                 db: Session = Depends(get_db)):
    """Cost rollup + budget status."""
    from app.db.migrate_phase4 import UsageRecord

    status = budget.get_status(db, ctx.company_id)
    plan = get_company_plan(db, ctx.company_id)

    # Last 30 days
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = db.query(
        UsageRecord.model,
        func.sum(UsageRecord.input_tokens).label("input_tokens"),
        func.sum(UsageRecord.output_tokens).label("output_tokens"),
        func.sum(UsageRecord.cost_usd).label("cost_usd"),
        func.count(UsageRecord.id).label("calls"),
    ).filter(
        UsageRecord.company_id == ctx.company_id,
        UsageRecord.created_at >= since,
    ).group_by(UsageRecord.model).all()

    by_model = []
    for r in rows:
        by_model.append({
            "model": r.model,
            "input_tokens": int(r.input_tokens or 0),
            "output_tokens": int(r.output_tokens or 0),
            "cost_usd": float(r.cost_usd or 0.0),
            "calls": int(r.calls or 0),
        })

    # Cache hit rate (last 30d)
    total_calls = db.query(func.count(UsageRecord.id)).filter(
        UsageRecord.company_id == ctx.company_id,
        UsageRecord.created_at >= since,
    ).scalar() or 0
    cache_hits = db.query(func.count(UsageRecord.id)).filter(
        UsageRecord.company_id == ctx.company_id,
        UsageRecord.created_at >= since,
        UsageRecord.was_cache_hit == True,
    ).scalar() or 0
    hit_rate = (cache_hits / total_calls * 100.0) if total_calls else 0.0

    return {
        "plan": plan_summary(plan),
        "budget": {
            "spent_usd": status.spent_usd,
            "budget_usd": status.budget_usd,
            "pct_used": status.pct_used,
            "can_use_cloud": status.can_use_cloud,
            "must_downgrade": status.must_downgrade,
        },
        "by_model": by_model,
        "cache": {
            "hit_rate_pct": round(hit_rate, 1),
            "total_calls_30d": int(total_calls),
            "cache_hits_30d": int(cache_hits),
        },
    }


@router.get("/cost/timeseries")
def cost_timeseries(days: int = 14,
                    ctx: CompanyContext = Depends(get_company_context),
                    db: Session = Depends(get_db)):
    """Daily cost for the last N days."""
    from app.db.migrate_phase4 import UsageRecord

    days = max(1, min(days, 90))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = db.query(
        func.date_trunc("day", UsageRecord.created_at).label("day"),
        func.sum(UsageRecord.cost_usd).label("cost_usd"),
        func.count(UsageRecord.id).label("calls"),
    ).filter(
        UsageRecord.company_id == ctx.company_id,
        UsageRecord.created_at >= since,
    ).group_by("day").order_by("day").all()

    return [
        {"day": r.day.date().isoformat() if r.day else None,
         "cost_usd": float(r.cost_usd or 0.0),
         "calls": int(r.calls or 0)}
        for r in rows
    ]


@router.get("/cache/stats")
def cache_stats(ctx: CompanyContext = Depends(get_company_context)):
    return cache.stats(ctx.company_id)


@router.delete("/cache")
def clear_cache(ctx: CompanyContext = Depends(get_company_context)):
    removed = cache.clear(ctx.company_id)
    return {"removed": removed}
