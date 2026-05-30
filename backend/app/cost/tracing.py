"""Trace spans — one row per LLM call.

A span tracks: model, latency, cost, cache hit, tokens, parent span (for the
manager → worker hierarchy). Frontend renders these as a DAG.
"""
from __future__ import annotations
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from sqlalchemy.orm import Session


@dataclass
class TraceContext:
    """Thread-local-ish trace context. Manager sets this; workers inherit."""
    company_id: int
    session_id: int | None = None
    parent_span_id: int | None = None
    agent_name: str | None = None


# Context var so async tasks inherit; each manager run sets it once.
_current: ContextVar[TraceContext | None] = ContextVar("trace_ctx", default=None)


def set_context(ctx: TraceContext | None):
    _current.set(ctx)


def get_context() -> TraceContext | None:
    return _current.get()


def child(agent_name: str) -> TraceContext | None:
    """Derive a child context for a worker call. Returns None if no parent."""
    parent = get_context()
    if parent is None:
        return None
    return TraceContext(
        company_id=parent.company_id,
        session_id=parent.session_id,
        parent_span_id=parent.parent_span_id,
        agent_name=agent_name,
    )


def start_span(db: Session, ctx: TraceContext, kind: str, model: str,
               input_preview: str = "") -> int:
    """Open a span and return its id."""
    from app.db.migrate_phase4 import TraceSpan
    span = TraceSpan(
        company_id=ctx.company_id,
        session_id=ctx.session_id,
        parent_span_id=ctx.parent_span_id,
        agent_name=ctx.agent_name,
        kind=kind,
        model=model,
        input_preview=(input_preview or "")[:500],
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(span)
    db.commit()
    db.refresh(span)
    return span.id


def end_span(db: Session, span_id: int, status: str, output_preview: str = "",
             input_tokens: int = 0, output_tokens: int = 0,
             cost_usd: float = 0.0, latency_ms: int = 0,
             was_cache_hit: bool = False, error: str | None = None):
    from app.db.migrate_phase4 import TraceSpan
    span = db.query(TraceSpan).get(span_id)
    if not span:
        return
    span.status = status
    span.output_preview = (output_preview or "")[:500]
    span.input_tokens = input_tokens
    span.output_tokens = output_tokens
    span.cost_usd = cost_usd
    span.latency_ms = latency_ms
    span.was_cache_hit = was_cache_hit
    span.error = error
    span.finished_at = datetime.utcnow()
    db.commit()


def list_spans_for_session(db: Session, session_id: int, company_id: int):
    from app.db.migrate_phase4 import TraceSpan
    rows = db.query(TraceSpan).filter(
        TraceSpan.session_id == session_id,
        TraceSpan.company_id == company_id,
    ).order_by(TraceSpan.id).all()
    return [_row_to_dict(s) for s in rows]


def list_spans_for_company(db: Session, company_id: int, limit: int = 200):
    from app.db.migrate_phase4 import TraceSpan
    rows = db.query(TraceSpan).filter(
        TraceSpan.company_id == company_id,
    ).order_by(TraceSpan.id.desc()).limit(limit).all()
    return [_row_to_dict(s) for s in rows]


def _row_to_dict(s):
    return {
        "id": s.id,
        "company_id": s.company_id,
        "session_id": s.session_id,
        "parent_span_id": s.parent_span_id,
        "agent_name": s.agent_name,
        "kind": s.kind,
        "model": s.model,
        "input_preview": s.input_preview,
        "output_preview": s.output_preview,
        "input_tokens": s.input_tokens or 0,
        "output_tokens": s.output_tokens or 0,
        "cost_usd": float(s.cost_usd or 0.0),
        "latency_ms": s.latency_ms or 0,
        "was_cache_hit": bool(s.was_cache_hit),
        "status": s.status,
        "error": s.error,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "finished_at": s.finished_at.isoformat() if s.finished_at else None,
    }
