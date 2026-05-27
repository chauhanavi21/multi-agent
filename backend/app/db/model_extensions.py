"""Phase 3 augments existing Phase 1+2 SQLAlchemy models with company_id.

The migration adds the column at the DB level (via ALTER TABLE); this module
adds the attribute at the model level so SQLAlchemy can query by it.

Import this module anywhere that needs the augmented models.
"""
from sqlalchemy import Column, Integer, ForeignKey

from app.db import models as p1_models
from app.db import migrate_phase2 as p2_models


# Only add the attribute if it isn't already there (idempotent for reloads)
if not hasattr(p1_models.Lead, "company_id"):
    p1_models.Lead.company_id = Column(Integer, ForeignKey("companies.id"))

if not hasattr(p1_models.EmailDraft, "company_id"):
    p1_models.EmailDraft.company_id = Column(Integer, ForeignKey("companies.id"))

# ChatSession already has a `company_id` column from Phase 2 (a plain int).
# Phase 2's column is what we'll keep using — the migration only added an _fk
# variant for future strict FK enforcement. Use the existing column at the
# ORM level so Phase 2 sessions queries keep working.
# (No model change needed for ChatSession.)
