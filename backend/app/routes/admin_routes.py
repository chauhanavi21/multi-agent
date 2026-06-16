"""Admin routes — Phase 6: adds ICP profile + scheduler_enabled toggle."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.db.migrate_phase3 import User, Company
from app.db.org_chart import get_locked_template
from app.auth.deps import get_admin_user
from app.agents import registry
from app.billing.plans import apply_plan_to_company, plan_summary


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_admin_user)])


class SetActiveRequest(BaseModel):
    is_active: bool


class OrgChartOverrideRequest(BaseModel):
    org_chart: dict


class CloudToggleRequest(BaseModel):
    use_cloud_api: bool


class BudgetRequest(BaseModel):
    monthly_budget_usd: float = Field(ge=0, le=10000)


class CloudProviderRequest(BaseModel):
    cloud_provider: str = Field(pattern="^(anthropic|bedrock)$")


class IcpProfileRequest(BaseModel):
    icp_profile: str = Field(max_length=4000)


class SchedulerToggleRequest(BaseModel):
    enabled: bool


class PlanRequest(BaseModel):
    plan: str = Field(pattern="^(free|pro|team)$")


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
            "use_cloud_api": bool(getattr(c, "use_cloud_api", False)),
            "monthly_budget_usd": float(getattr(c, "monthly_budget_usd", 0) or 0),
            "cloud_provider": getattr(c, "cloud_provider", None) or "anthropic",
            "icp_profile": getattr(c, "icp_profile", None) or "",
            "scheduler_enabled": bool(getattr(c, "scheduler_enabled", False)),
            "plan": getattr(c, "plan", None) or "free",
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


@router.get("/template")
def get_template():
    return {
        "template": get_locked_template(),
        "available_agents": [w.spec.name for w in registry.list_workers()],
    }


@router.put("/companies/{company_id}/org_chart")
def set_company_org_chart(company_id: int, payload: OrgChartOverrideRequest,
                          db: Session = Depends(get_db)):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c: raise HTTPException(404, "Company not found")
    valid = {w.spec.name for w in registry.list_workers()}
    for name, count in payload.org_chart.items():
        if name not in valid:
            raise HTTPException(400, f"Unknown agent: {name}")
        if not isinstance(count, int) or count < 0 or count > 10:
            raise HTTPException(400, f"Invalid count for {name}")
    c.org_chart_override = payload.org_chart
    db.commit()
    return {"ok": True, "org_chart": c.org_chart_override}


@router.delete("/companies/{company_id}/org_chart")
def reset_company_org_chart(company_id: int, db: Session = Depends(get_db)):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c: raise HTTPException(404, "Company not found")
    c.org_chart_override = None
    db.commit()
    return {"ok": True, "org_chart": get_locked_template()}


@router.put("/companies/{company_id}/cloud")
def set_cloud_toggle(company_id: int, payload: CloudToggleRequest,
                     db: Session = Depends(get_db)):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c: raise HTTPException(404, "Company not found")
    c.use_cloud_api = payload.use_cloud_api
    db.commit()
    return {"ok": True, "use_cloud_api": c.use_cloud_api}


@router.put("/companies/{company_id}/budget")
def set_budget(company_id: int, payload: BudgetRequest,
               db: Session = Depends(get_db)):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c: raise HTTPException(404, "Company not found")
    c.monthly_budget_usd = payload.monthly_budget_usd
    db.commit()
    return {"ok": True, "monthly_budget_usd": float(c.monthly_budget_usd)}


@router.put("/companies/{company_id}/cloud_provider")
def set_cloud_provider(company_id: int, payload: CloudProviderRequest,
                       db: Session = Depends(get_db)):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c: raise HTTPException(404, "Company not found")
    c.cloud_provider = payload.cloud_provider
    db.commit()
    return {"ok": True, "cloud_provider": c.cloud_provider}


# ===== Phase 6 =====

@router.put("/companies/{company_id}/icp_profile")
def set_icp_profile(company_id: int, payload: IcpProfileRequest,
                    db: Session = Depends(get_db)):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c: raise HTTPException(404, "Company not found")
    c.icp_profile = payload.icp_profile
    db.commit()
    return {"ok": True, "icp_profile": c.icp_profile}


@router.put("/companies/{company_id}/scheduler")
def set_scheduler_toggle(company_id: int, payload: SchedulerToggleRequest,
                         db: Session = Depends(get_db)):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c: raise HTTPException(404, "Company not found")
    c.scheduler_enabled = payload.enabled
    db.commit()
    return {"ok": True, "scheduler_enabled": c.scheduler_enabled}


@router.put("/companies/{company_id}/plan")
def set_company_plan(company_id: int, payload: PlanRequest,
                     db: Session = Depends(get_db)):
    """Set subscription plan and sync cloud toggle + monthly budget."""
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(404, "Company not found")
    apply_plan_to_company(c, payload.plan)  # type: ignore[arg-type]
    db.commit()
    return {"ok": True, **plan_summary(payload.plan)}  # type: ignore[arg-type]


@router.get("/plans")
def list_plans():
    """Plan catalog for admin UI / future billing page."""
    return [plan_summary(name) for name in ("free", "pro", "team")]
