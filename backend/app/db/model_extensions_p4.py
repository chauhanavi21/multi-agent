"""Adds Phase 4 columns to the Company SQLAlchemy model.

The migration adds the columns at the DB level; this module adds them at the
ORM level so queries can use them. Same pattern as Phase 3's model_extensions.
"""
from sqlalchemy import Column, Boolean, Numeric
from app.db import migrate_phase3 as p3_models


if not hasattr(p3_models.Company, "use_cloud_api"):
    p3_models.Company.use_cloud_api = Column(Boolean, default=False, nullable=False)

if not hasattr(p3_models.Company, "monthly_budget_usd"):
    p3_models.Company.monthly_budget_usd = Column(Numeric(10, 2), default=5.0, nullable=False)
