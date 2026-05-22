"""Tools the sales agent can call on the lead DB."""
import json
from typing import Optional
from sqlalchemy.orm import Session
from app.db.models import Lead


def search_leads(db: Session, criteria: Optional[str] = None, limit: int = 10):
    """Return leads. If criteria provided, filter by industry/title/company substring."""
    q = db.query(Lead)
    if criteria:
        c = f"%{criteria.lower()}%"
        q = q.filter(
            (Lead.industry.ilike(c))
            | (Lead.title.ilike(c))
            | (Lead.company.ilike(c))
        )
    leads = q.order_by(Lead.created_at.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "name": l.name,
            "title": l.title,
            "company": l.company,
            "industry": l.industry,
            "email": l.email,
            "notes": l.notes,
            "status": l.status,
        }
        for l in leads
    ]


def get_lead(db: Session, lead_id: int):
    l = db.query(Lead).filter(Lead.id == lead_id).first()
    if not l:
        return None
    return {
        "id": l.id, "name": l.name, "title": l.title, "company": l.company,
        "industry": l.industry, "email": l.email, "notes": l.notes,
        "status": l.status,
    }


def add_lead(db: Session, lead: dict):
    """Add a single new lead. Used by generate_leads agent task."""
    obj = Lead(
        name=lead["name"],
        title=lead["title"],
        company=lead["company"],
        industry=lead.get("industry", ""),
        email=lead["email"],
        notes=lead.get("notes", ""),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj.id
