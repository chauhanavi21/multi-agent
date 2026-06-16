"""Adds Phase 6 columns to Company and Lead ORM models."""
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime
from app.db import migrate_phase3 as p3_models
from app.db.models import Lead


# Company
if not hasattr(p3_models.Company, "icp_profile"):
    p3_models.Company.icp_profile = Column(Text, nullable=True)
if not hasattr(p3_models.Company, "scheduler_enabled"):
    p3_models.Company.scheduler_enabled = Column(Boolean, default=False, nullable=False)

# Lead
if not hasattr(Lead, "icp_score"):
    Lead.icp_score = Column(Integer, nullable=True)
if not hasattr(Lead, "current_stage"):
    Lead.current_stage = Column(String(40), nullable=True)
if not hasattr(Lead, "last_contacted_at"):
    Lead.last_contacted_at = Column(DateTime, nullable=True)
if not hasattr(Lead, "next_followup_at"):
    Lead.next_followup_at = Column(DateTime, nullable=True)
