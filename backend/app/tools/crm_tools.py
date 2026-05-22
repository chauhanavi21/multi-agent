"""CRM-style tools for tracking outreach activity."""
from sqlalchemy.orm import Session
from app.db.models import Lead


def log_followup(db: Session, lead_id: int, new_status: str) -> dict:
    valid = {"new", "contacted", "replied", "lost", "won"}
    if new_status not in valid:
        return {"ok": False, "error": f"invalid status (use one of {valid})"}
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"ok": False, "error": "lead not found"}
    lead.status = new_status
    db.commit()
    return {"ok": True, "lead_id": lead_id, "status": new_status}
