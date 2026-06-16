"""Stripe Checkout, Customer Portal, and webhook handling."""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.billing.plans import PlanName, apply_plan_to_company, plan_summary, PLANS

log = logging.getLogger(__name__)

PLAN_PRICE_SETTING = {
    "pro": "stripe_price_id_pro",
    "team": "stripe_price_id_team",
}


def stripe_enabled() -> bool:
    return bool(settings.stripe_secret_key and settings.stripe_webhook_secret)


def _stripe():
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Billing is not configured on this server.")
    import stripe
    stripe.api_key = settings.stripe_secret_key
    return stripe


def price_id_for_plan(plan: PlanName) -> str:
    if plan == "free":
        raise HTTPException(400, "Free plan does not require checkout.")
    attr = PLAN_PRICE_SETTING.get(plan)
    if not attr:
        raise HTTPException(400, f"Unknown plan: {plan}")
    pid = getattr(settings, attr, "")
    if not pid:
        raise HTTPException(
            503,
            f"Stripe price for '{plan}' is not configured. Set {attr.upper()} in the server environment.",
        )
    return pid


def create_checkout_session(
    db: Session,
    *,
    company_id: int,
    plan: PlanName,
    customer_email: str,
) -> dict:
    from app.db.migrate_phase3 import Company

    if plan not in ("pro", "team"):
        raise HTTPException(400, "Only pro or team plans can be purchased.")

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    stripe = _stripe()
    price_id = price_id_for_plan(plan)
    base = settings.frontend_base_url.rstrip("/")

    kwargs = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{base}/?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/?billing=cancel",
        "metadata": {"company_id": str(company_id), "plan": plan},
        "subscription_data": {"metadata": {"company_id": str(company_id), "plan": plan}},
    }
    if company.stripe_customer_id:
        kwargs["customer"] = company.stripe_customer_id
    else:
        kwargs["customer_email"] = customer_email

    session = stripe.checkout.Session.create(**kwargs)
    return {"checkout_url": session.url, "session_id": session.id}


def create_portal_session(db: Session, company_id: int) -> dict:
    from app.db.migrate_phase3 import Company

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company or not company.stripe_customer_id:
        raise HTTPException(400, "No billing account linked. Subscribe to a paid plan first.")

    stripe = _stripe()
    base = settings.frontend_base_url.rstrip("/")
    session = stripe.billing_portal.Session.create(
        customer=company.stripe_customer_id,
        return_url=f"{base}/",
    )
    return {"portal_url": session.url}


def _apply_subscription(db: Session, company_id: int, plan: PlanName,
                        customer_id: Optional[str], subscription_id: Optional[str]) -> None:
    from app.db.migrate_phase3 import Company

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        log.warning("stripe webhook: company %s not found", company_id)
        return
    if customer_id:
        company.stripe_customer_id = customer_id
    if subscription_id:
        company.stripe_subscription_id = subscription_id
    apply_plan_to_company(company, plan)
    db.commit()
    log.info("Applied plan %s to company %s via Stripe", plan, company_id)


def _downgrade_to_free(db: Session, company_id: int) -> None:
    from app.db.migrate_phase3 import Company

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return
    company.stripe_subscription_id = None
    apply_plan_to_company(company, "free")
    db.commit()
    log.info("Downgraded company %s to free after subscription ended", company_id)


def handle_webhook(payload: bytes, sig_header: Optional[str], db: Session) -> dict:
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "Stripe webhook secret is not configured.")

    stripe = _stripe()
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret,
        )
    except Exception as e:
        log.warning("stripe webhook verify failed: %s", e)
        raise HTTPException(400, "Invalid webhook signature") from e

    etype = event["type"]
    data = event["data"]["object"]

    if etype == "checkout.session.completed":
        meta = data.get("metadata") or {}
        company_id = int(meta.get("company_id", 0))
        plan = meta.get("plan", "pro")
        if company_id and plan in PLANS:
            _apply_subscription(
                db, company_id, plan,  # type: ignore[arg-type]
                customer_id=data.get("customer"),
                subscription_id=data.get("subscription"),
            )

    elif etype in ("customer.subscription.updated", "customer.subscription.created"):
        meta = data.get("metadata") or {}
        company_id = int(meta.get("company_id", 0))
        plan = meta.get("plan", "pro")
        status = data.get("status", "")
        if company_id and status in ("active", "trialing") and plan in PLANS:
            _apply_subscription(
                db, company_id, plan,  # type: ignore[arg-type]
                customer_id=data.get("customer"),
                subscription_id=data.get("id"),
            )
        elif company_id and status in ("canceled", "unpaid", "past_due"):
            # Keep plan until explicitly deleted; past_due could notify user
            pass

    elif etype == "customer.subscription.deleted":
        meta = data.get("metadata") or {}
        company_id = int(meta.get("company_id", 0))
        if company_id:
            _downgrade_to_free(db, company_id)

    return {"received": True, "type": etype}


def billing_catalog() -> list[dict]:
    items = []
    for name in ("free", "pro", "team"):
        row = plan_summary(name)  # type: ignore[arg-type]
        row["checkout_available"] = (
            stripe_enabled()
            and name in ("pro", "team")
            and bool(getattr(settings, PLAN_PRICE_SETTING[name], ""))
        )
        items.append(row)
    return items
