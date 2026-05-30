"""Phase 4 migration.

Adds:
  - usage_records  (one row per LLM call; for budget rollups + analytics)
  - traces         (one row per span; for the trace UI)

Augments companies:
  - use_cloud_api boolean      (off by default)
  - monthly_budget_usd numeric (default $5)

Run: python -m app.db.migrate_phase4
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Numeric, Index, text,
)
from app.db.models import Base, engine
# Import Phase 3 models so SQLAlchemy is aware of the companies table the FKs reference
from app.db import migrate_phase3  # noqa: F401


class UsageRecord(Base):
    __tablename__ = "usage_records"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    model = Column(String(80), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Numeric(10, 6), default=0)
    agent_name = Column(String(60), nullable=True)
    trace_span_id = Column(Integer, nullable=True)
    was_cache_hit = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class TraceSpan(Base):
    __tablename__ = "traces"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    session_id = Column(Integer, nullable=True, index=True)
    parent_span_id = Column(Integer, nullable=True)
    agent_name = Column(String(60), nullable=True)
    kind = Column(String(40), default="llm")    # llm, tool, manager, worker
    model = Column(String(80), nullable=True)
    input_preview = Column(Text, nullable=True)
    output_preview = Column(Text, nullable=True)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Numeric(10, 6), default=0)
    latency_ms = Column(Integer, default=0)
    was_cache_hit = Column(Boolean, default=False)
    status = Column(String(20), default="running")
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


Index("ix_usage_company_month", UsageRecord.company_id, UsageRecord.created_at)
Index("ix_traces_company_session", TraceSpan.company_id, TraceSpan.session_id)


ALTER_SQL = [
    'ALTER TABLE companies ADD COLUMN IF NOT EXISTS use_cloud_api BOOLEAN DEFAULT FALSE NOT NULL',
    'ALTER TABLE companies ADD COLUMN IF NOT EXISTS monthly_budget_usd NUMERIC(10,2) DEFAULT 5.0 NOT NULL',
]


def main():
    print("Creating Phase 4 tables (usage_records, traces)...")
    Base.metadata.create_all(bind=engine, tables=[
        UsageRecord.__table__,
        TraceSpan.__table__,
    ])
    print("Altering companies (use_cloud_api, monthly_budget_usd)...")
    with engine.begin() as conn:
        for stmt in ALTER_SQL:
            conn.execute(text(stmt))
    print("Done.")


if __name__ == "__main__":
    main()
