"""Tools for drafting and sending outreach emails."""
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.models import EmailDraft, Lead


def save_draft(db: Session, lead_id: int, subject: str, body: str) -> int:
    draft = EmailDraft(lead_id=lead_id, subject=subject, body=body, status="draft")
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft.id


def update_draft(db: Session, draft_id: int, subject: str, body: str):
    d = db.query(EmailDraft).filter(EmailDraft.id == draft_id).first()
    if not d:
        return None
    d.subject = subject
    d.body = body
    db.commit()
    return d.id


def send_email(db: Session, draft_id: int) -> dict:
    """Mock send — flips status to 'sent' and updates lead status to 'contacted'.
    Wire to SendGrid/SES/SMTP later by replacing this function body."""
    d = db.query(EmailDraft).filter(EmailDraft.id == draft_id).first()
    if not d:
        return {"ok": False, "error": "draft not found"}
    d.status = "sent"
    d.sent_at = datetime.utcnow()
    lead = db.query(Lead).filter(Lead.id == d.lead_id).first()
    if lead:
        lead.status = "contacted"
    db.commit()
    return {"ok": True, "draft_id": draft_id, "sent_at": d.sent_at.isoformat()}


def list_drafts(db: Session, lead_id: int):
    drafts = db.query(EmailDraft).filter(EmailDraft.lead_id == lead_id).order_by(
        EmailDraft.created_at.desc()
    ).all()
    return [
        {
            "id": d.id, "subject": d.subject, "body": d.body,
            "status": d.status,
            "sent_at": d.sent_at.isoformat() if d.sent_at else None,
            "created_at": d.created_at.isoformat(),
        }
        for d in drafts
    ]
