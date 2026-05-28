"""Admin-only routes — manage users, companies, and the global org chart template."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.db.migrate_phase3 import User, Company
from app.db.org_chart import get_locked_template
from app.auth.deps import get_admin_user
from app.agents import registry


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_admin_user)])


class SetActiveRequest(BaseModel):
    is_active: bool


class OrgChartOverrideRequest(BaseModel):
    org_chart: dict   # agent_name -> count


@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    rows = db.query(User).order_by(User.id).all()
    return [
        {
            "id": u.id, "email": u.email, "full_name": u.full_name,
            "is_admin": u.is_admin, "is_active": u.is_active,
            "company_id": u.company_id,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        }
        for u in rows
    ]


@router.put("/users/{user_id}/active")
def set_user_active(user_id: int, payload: SetActiveRequest, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    if u.is_admin and not payload.is_active:
        raise HTTPException(400, "Cannot deactivate an admin user")
    u.is_active = payload.is_active
    db.commit()
    return {"ok": True, "user_id": u.id, "is_active": u.is_active}


@router.get("/companies")
def list_companies(db: Session = Depends(get_db)):
    rows = db.query(Company).order_by(Company.id).all()
    return [
        {
            "id": c.id, "name": c.name, "owner_user_id": c.owner_user_id,
            "org_chart_override": c.org_chart_override,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


@router.get("/template")
def get_template():
    """Get the default global org chart template + list of available agents."""
    return {
        "template": get_locked_template(),
        "available_agents": [w.spec.name for w in registry.list_workers()],
    }


@router.put("/companies/{company_id}/org_chart")
def set_company_org_chart(company_id: int, payload: OrgChartOverrideRequest,
                          db: Session = Depends(get_db)):
    """Admin can override the org chart for a specific company."""
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(404, "Company not found")

    # Validate: every agent in the override must exist in the registry
    valid = {w.spec.name for w in registry.list_workers()}
    for name, count in payload.org_chart.items():
        if name not in valid:
            raise HTTPException(400, f"Unknown agent: {name}")
        if not isinstance(count, int) or count < 0 or count > 10:
            raise HTTPException(400, f"Invalid count for {name}: must be int 0-10")

    c.org_chart_override = payload.org_chart
    db.commit()
    return {"ok": True, "company_id": c.id, "org_chart": c.org_chart_override}


@router.delete("/companies/{company_id}/org_chart")
def reset_company_org_chart(company_id: int, db: Session = Depends(get_db)):
    """Reset a company back to the default locked template."""
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(404, "Company not found")
    c.org_chart_override = None
    db.commit()
    return {"ok": True, "company_id": c.id, "org_chart": get_locked_template()}
