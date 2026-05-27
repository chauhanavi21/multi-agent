"""Tools the sales agent can call on the lead DB. All queries are company-scoped."""
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.db.models import Lead


def search_leads(db: Session, company_id: int, criteria: Optional[str] = None, limit: int = 10):
    """Return leads for a specific company. If criteria provided, filter further."""
    q = db.query(Lead).filter(Lead.company_id == company_id)
    if criteria:
        c = f"%{criteria.lower()}%"
        q = q.filter(or_(
            Lead.industry.ilike(c),
            Lead.title.ilike(c),
            Lead.company.ilike(c),
        ))
    leads = q.order_by(Lead.created_at.desc()).limit(limit).all()
    return [
        {
            "id": l.id, "name": l.name, "title": l.title, "company": l.company,
            "industry": l.industry, "email": l.email, "notes": l.notes,
            "status": l.status,
        }
        for l in leads
    ]


def get_lead(db: Session, company_id: int, lead_id: int):
    l = db.query(Lead).filter(Lead.id == lead_id, Lead.company_id == company_id).first()
    if not l:
        return None
    return {
        "id": l.id, "name": l.name, "title": l.title, "company": l.company,
        "industry": l.industry, "email": l.email, "notes": l.notes,
        "status": l.status,
    }


def add_lead(db: Session, company_id: int, lead: dict):
    """Add a single new lead under a company."""
    obj = Lead(
        name=lead["name"],
        title=lead["title"],
        company=lead["company"],
        industry=lead.get("industry", ""),
        email=lead["email"],
        notes=lead.get("notes", ""),
        company_id=company_id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj.id
