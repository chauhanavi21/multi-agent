"""Lead pipeline helpers: stage transitions, ICP scoring, follow-up scheduling."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from app.db.models import SessionLocal, Lead


STAGES = ("new", "qualified", "contacted", "in_conversation", "won", "lost")


def transition(company_id: int, lead_id: int, to_stage: str,
               reason: str | None = None, agent: str | None = None) -> dict:
    if to_stage not in STAGES:
        return {"ok": False, "error": f"unknown stage: {to_stage}"}
    from app.db.migrate_phase6 import LeadStageHistory
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.company_id == company_id).first()
        if not lead:
            return {"ok": False, "error": "lead not found"}
        from_stage = getattr(lead, "current_stage", None) or lead.status
        hist = LeadStageHistory(
            company_id=company_id, lead_id=lead_id,
            from_stage=from_stage, to_stage=to_stage,
            reason=reason, changed_by_agent=agent,
        )
        db.add(hist)
        lead.current_stage = to_stage
        # Keep .status in sync for backward compatibility with Phase 1 UI
        lead.status = to_stage
        db.commit()
        return {"ok": True, "lead_id": lead_id,
                "from_stage": from_stage, "to_stage": to_stage}
    finally:
        db.close()


def set_icp_score(company_id: int, lead_id: int, score: int,
                  rationale: str | None = None) -> dict:
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.company_id == company_id).first()
        if not lead:
            return {"ok": False, "error": "lead not found"}
        lead.icp_score = max(0, min(100, int(score)))
        db.commit()
        return {"ok": True, "lead_id": lead_id, "icp_score": lead.icp_score,
                "rationale": rationale}
    finally:
        db.close()


def schedule_followup(company_id: int, lead_id: int, days: int = 3) -> dict:
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.company_id == company_id).first()
        if not lead:
            return {"ok": False, "error": "lead not found"}
        lead.next_followup_at = datetime.utcnow() + timedelta(days=days)
        db.commit()
        return {"ok": True, "lead_id": lead_id,
                "next_followup_at": lead.next_followup_at.isoformat()}
    finally:
        db.close()


def mark_contacted(company_id: int, lead_id: int) -> None:
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.company_id == company_id).first()
        if not lead:
            return
        lead.last_contacted_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def leads_due_for_followup(company_id: int, limit: int = 20) -> list[Lead]:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        rows = db.query(Lead).filter(
            Lead.company_id == company_id,
            Lead.next_followup_at != None,   # noqa: E711
            Lead.next_followup_at <= now,
        ).order_by(Lead.next_followup_at.asc()).limit(limit).all()
        return rows
    finally:
        db.close()


def stage_history(company_id: int, lead_id: int) -> list[dict]:
    from app.db.migrate_phase6 import LeadStageHistory
    db = SessionLocal()
    try:
        rows = db.query(LeadStageHistory).filter(
            LeadStageHistory.company_id == company_id,
            LeadStageHistory.lead_id == lead_id,
        ).order_by(LeadStageHistory.id).all()
        return [
            {
                "id": r.id, "from_stage": r.from_stage, "to_stage": r.to_stage,
                "reason": r.reason, "agent": r.changed_by_agent,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()
