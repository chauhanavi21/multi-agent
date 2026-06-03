"""Adds Phase 5 column to the Company SQLAlchemy model."""
from sqlalchemy import Column, String
from app.db import migrate_phase3 as p3_models


if not hasattr(p3_models.Company, "cloud_provider"):
    p3_models.Company.cloud_provider = Column(String(20), default="anthropic", nullable=False)
