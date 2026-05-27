"""Tools for drafting and sending outreach emails. Company-scoped."""
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.models import EmailDraft, Lead


def _verify_lead_in_company(db: Session, lead_id: int, company_id: int) -> bool:
    return db.query(Lead).filter(
        Lead.id == lead_id, Lead.company_id == company_id
    ).first() is not None


def _verify_draft_in_company(db: Session, draft_id: int, company_id: int) -> EmailDraft | None:
    return (
        db.query(EmailDraft)
        .join(Lead, Lead.id == EmailDraft.lead_id)
        .filter(EmailDraft.id == draft_id, Lead.company_id == company_id)
        .first()
    )


def save_draft(db: Session, company_id: int, lead_id: int, subject: str, body: str) -> int | None:
    if not _verify_lead_in_company(db, lead_id, company_id):
        return None
    draft = EmailDraft(lead_id=lead_id, subject=subject, body=body, status="draft",
                       company_id=company_id)
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft.id


def update_draft(db: Session, company_id: int, draft_id: int, subject: str, body: str):
    d = _verify_draft_in_company(db, draft_id, company_id)
    if not d:
        return None
    d.subject = subject
    d.body = body
    db.commit()
    return d.id


def send_email(db: Session, company_id: int, draft_id: int) -> dict:
    """Mock send — flips status to 'sent' and updates lead status to 'contacted'."""
    d = _verify_draft_in_company(db, draft_id, company_id)
    if not d:
        return {"ok": False, "error": "draft not found"}
    d.status = "sent"
    d.sent_at = datetime.utcnow()
    lead = db.query(Lead).filter(Lead.id == d.lead_id, Lead.company_id == company_id).first()
    if lead:
        lead.status = "contacted"
    db.commit()
    return {"ok": True, "draft_id": draft_id, "sent_at": d.sent_at.isoformat()}


def list_drafts(db: Session, company_id: int, lead_id: int):
    if not _verify_lead_in_company(db, lead_id, company_id):
        return []
    drafts = db.query(EmailDraft).filter(
        EmailDraft.lead_id == lead_id, EmailDraft.company_id == company_id
    ).order_by(EmailDraft.created_at.desc()).all()
    return [
        {
            "id": d.id, "subject": d.subject, "body": d.body,
            "status": d.status,
            "sent_at": d.sent_at.isoformat() if d.sent_at else None,
            "created_at": d.created_at.isoformat(),
        }
        for d in drafts
    ]
