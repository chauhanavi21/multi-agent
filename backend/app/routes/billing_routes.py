"""Billing — usage, Stripe checkout, portal, webhooks."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.auth.deps import get_company_context, CompanyContext
from app.billing.plans import get_company_plan, plan_summary
from app.billing.limits import chat_limit_status
from app.billing import stripe_service

router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    plan: str = Field(pattern="^(pro|team)$")


@router.get("/plans")
def list_plans():
    """Public plan catalog with Stripe checkout availability."""
    return {
        "stripe_enabled": stripe_service.stripe_enabled(),
        "plans": stripe_service.billing_catalog(),
    }


@router.get("/usage")
def billing_usage(ctx: CompanyContext = Depends(get_company_context),
                  db: Session = Depends(get_db)):
    from app.db.migrate_phase3 import Company

    plan = get_company_plan(db, ctx.company_id)
    company = db.query(Company).filter(Company.id == ctx.company_id).first()
    return {
        "plan": plan_summary(plan),
        "chat_hourly": chat_limit_status(ctx.company_id, plan),
        "stripe_enabled": stripe_service.stripe_enabled(),
        "billing": {
            "has_stripe_customer": bool(company and company.stripe_customer_id),
            "has_active_subscription": bool(company and company.stripe_subscription_id),
        },
    }


@router.post("/checkout")
def start_checkout(payload: CheckoutRequest,
                   ctx: CompanyContext = Depends(get_company_context),
                   db: Session = Depends(get_db)):
    if ctx.user.is_admin and not ctx.company_id:
        raise HTTPException(400, "Admin users without a company cannot subscribe.")
    return stripe_service.create_checkout_session(
        db,
        company_id=ctx.company_id,
        plan=payload.plan,  # type: ignore[arg-type]
        customer_email=ctx.user.email,
    )


@router.post("/portal")
def billing_portal(ctx: CompanyContext = Depends(get_company_context),
                   db: Session = Depends(get_db)):
    return stripe_service.create_portal_session(db, ctx.company_id)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe sends events here — no JWT. Verify signature instead."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    return stripe_service.handle_webhook(payload, sig, db)
