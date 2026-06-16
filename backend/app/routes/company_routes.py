"""Company-scoped routes — read-only for users, view org chart, team roster."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.db.org_chart import get_locked_template
from app.auth.deps import get_company_context, CompanyContext
from app.agents import registry
from app.billing.plans import plan_summary


router = APIRouter(prefix="/api/company", tags=["company"])


@router.get("/me")
def my_company(ctx: CompanyContext = Depends(get_company_context)):
    """Get the calling user's company info + effective org chart."""
    company = ctx.company
    template = company.org_chart_override or get_locked_template()
    return {
        "id": company.id,
        "name": company.name,
        "plan": plan_summary(getattr(company, "plan", None) or "free"),
        "org_chart": template,
        "is_locked": True,    # users cannot edit
        "is_admin_override": ctx.is_admin_override,
    }


@router.get("/team")
def team(ctx: CompanyContext = Depends(get_company_context)):
    """Resolved team — combines org chart counts with agent registry capabilities."""
    template = ctx.company.org_chart_override or get_locked_template()
    chart = registry.org_chart()
    # Filter to agents that are in this company's template
    chart_by_name = {a["name"]: a for a in chart}
    team = []
    for name, count in template.items():
        if name in chart_by_name:
            team.append({**chart_by_name[name], "count": count})
    return {"company_id": ctx.company_id, "team": team}
