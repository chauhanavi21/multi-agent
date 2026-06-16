"""Billing usage endpoints for the current company."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.auth.deps import get_company_context, CompanyContext
from app.billing.plans import get_company_plan, plan_summary
from app.billing.limits import chat_limit_status

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/usage")
def billing_usage(ctx: CompanyContext = Depends(get_company_context),
                  db: Session = Depends(get_db)):
    plan = get_company_plan(db, ctx.company_id)
    return {
        "plan": plan_summary(plan),
        "chat_hourly": chat_limit_status(ctx.company_id, plan),
    }
