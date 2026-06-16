"""Adds Phase 7 plan column to the Company SQLAlchemy model."""
from sqlalchemy import Column, String
from app.db import migrate_phase3 as p3_models


if not hasattr(p3_models.Company, "plan"):
    p3_models.Company.plan = Column(String(20), default="free", nullable=False)
