"""Phase 8 — Stripe IDs on Company, terms acceptance on User."""
from sqlalchemy import Column, String, DateTime
from app.db import migrate_phase3 as p3_models

if not hasattr(p3_models.Company, "stripe_customer_id"):
    p3_models.Company.stripe_customer_id = Column(String(80), nullable=True)
if not hasattr(p3_models.Company, "stripe_subscription_id"):
    p3_models.Company.stripe_subscription_id = Column(String(80), nullable=True)
if not hasattr(p3_models.User, "terms_accepted_at"):
    p3_models.User.terms_accepted_at = Column(DateTime(timezone=True), nullable=True)
