"""Phase 6 migration.

Adds:
  - memories            : the shared learning store (pgvector OR numpy mode)
  - lead_stage_history  : every transition logged
  - daily_plans         : CEO output, one per company per day
  - competitor_reels    : mock + apify-scraped reel data
  - reel_scripts        : CMO-generated reel scripts
  - sms_outbox          : SMS sends (mock or via Twilio)
  - scheduler_jobs      : per-company scheduler config

Augments:
  - leads               : adds icp_score, current_stage, last_contacted_at, next_followup_at
  - companies           : adds icp_profile (text), scheduler_enabled (bool)

Phase 6 also detects pgvector support at migration time:
  - tries CREATE EXTENSION IF NOT EXISTS vector
  - if OK, adds memories.embedding_vec vector(768) + IVFFlat index
  - if not, leaves embedding stored only as JSON text (numpy backend handles it)

Run: python -m app.db.migrate_phase6
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    Numeric, Float, Index, text, JSON, LargeBinary,
)
from app.db.models import Base, engine
# Make sure earlier-phase models are loaded so SQLAlchemy knows about companies/leads/etc.
from app.db import migrate_phase2  # noqa: F401
from app.db import migrate_phase3  # noqa: F401
from app.db import migrate_phase4  # noqa: F401


# ===== Memories =====
class Memory(Base):
    __tablename__ = "memories"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    kind = Column(String(40), nullable=False, index=True)  # lesson|pattern|fact|preference|competitor|win|loss
    content = Column(Text, nullable=False)
    tags = Column(JSON, default=list)
    source_agent = Column(String(60), nullable=True)
    source_session_id = Column(Integer, nullable=True)
    outcome = Column(String(40), nullable=True)
    importance = Column(Float, default=0.5, nullable=False)
    access_count = Column(Integer, default=0, nullable=False)
    last_accessed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    # numpy-backend: embedding stored as raw bytes (np.float32.tobytes())
    embedding_bytes = Column(LargeBinary, nullable=True)
    embedding_dim = Column(Integer, nullable=True)


Index("ix_memories_company_kind", Memory.company_id, Memory.kind)


# ===== Lead stage history =====
class LeadStageHistory(Base):
    __tablename__ = "lead_stage_history"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    lead_id = Column(Integer, nullable=False, index=True)
    from_stage = Column(String(40), nullable=True)
    to_stage = Column(String(40), nullable=False)
    reason = Column(Text, nullable=True)
    changed_by_agent = Column(String(60), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


# ===== Daily plans =====
class DailyPlan(Base):
    __tablename__ = "daily_plans"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    plan_date = Column(String(10), nullable=False)   # ISO date YYYY-MM-DD
    summary = Column(Text, nullable=False)           # CEO's narrative
    priorities = Column(JSON, default=list)          # ["Generate 10 fintech leads", "Draft 3 reels", ...]
    metrics_yesterday = Column(JSON, default=dict)   # {leads_added: 5, drafts: 12, ...}
    spawned_session_ids = Column(JSON, default=list) # chat sessions the CEO opened to delegate
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index("ix_daily_plans_company_date", DailyPlan.company_id, DailyPlan.plan_date, unique=True)


# ===== Competitor reels =====
class CompetitorReel(Base):
    __tablename__ = "competitor_reels"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    platform = Column(String(20), nullable=False)   # instagram | facebook
    competitor_handle = Column(String(120), nullable=False)
    url = Column(String(500), nullable=True)
    caption = Column(Text, nullable=True)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    posted_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    source = Column(String(20), default="mock")     # mock | apify | manual


# ===== Reel scripts =====
class ReelScript(Base):
    __tablename__ = "reel_scripts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    hook = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    cta = Column(Text, nullable=True)
    inspired_by_reel_ids = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ===== SMS outbox =====
class SmsOutbox(Base):
    __tablename__ = "sms_outbox"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    lead_id = Column(Integer, nullable=True)
    to_number = Column(String(40), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(20), default="queued")  # queued | sent | failed | mock
    twilio_sid = Column(String(80), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)


# ===== Scheduler jobs =====
class SchedulerJob(Base):
    __tablename__ = "scheduler_jobs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    job_name = Column(String(60), nullable=False)   # ceo_daily | outreach_daily | cmo_daily | insights_daily
    cron_expr = Column(String(60), nullable=False)  # APScheduler-style
    enabled = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime, nullable=True)
    last_status = Column(String(20), nullable=True)  # ok | error
    last_error = Column(Text, nullable=True)


Index("ix_scheduler_company_job", SchedulerJob.company_id, SchedulerJob.job_name, unique=True)


ALTER_SQL = [
    # Leads
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS icp_score INTEGER",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS current_stage VARCHAR(40)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_contacted_at TIMESTAMP",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS next_followup_at TIMESTAMP",
    # Companies
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS icp_profile TEXT",
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS scheduler_enabled BOOLEAN DEFAULT FALSE NOT NULL",
]


def _detect_pgvector(conn) -> bool:
    """Try to enable pgvector. Returns True if it's available afterwards."""
    try:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Confirm
        row = conn.execute(text(
            "SELECT extname FROM pg_extension WHERE extname='vector'"
        )).first()
        return row is not None
    except Exception as e:
        print(f"pgvector not available: {e}")
        return False


def main():
    print("Creating Phase 6 tables...")
    Base.metadata.create_all(bind=engine, tables=[
        Memory.__table__,
        LeadStageHistory.__table__,
        DailyPlan.__table__,
        CompetitorReel.__table__,
        ReelScript.__table__,
        SmsOutbox.__table__,
        SchedulerJob.__table__,
    ])

    print("Altering leads, companies...")
    with engine.begin() as conn:
        for stmt in ALTER_SQL:
            conn.execute(text(stmt))

    print("Detecting pgvector...")
    with engine.begin() as conn:
        has_pgvector = _detect_pgvector(conn)
        if has_pgvector:
            print("  pgvector available — adding embedding_vec column + ivfflat index")
            try:
                conn.execute(text(
                    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding_vec vector(768)"
                ))
                # IVFFlat needs data to build the index well, but creating with empty is fine
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_memories_embedding_vec "
                    "ON memories USING ivfflat (embedding_vec vector_cosine_ops) WITH (lists = 100)"
                ))
            except Exception as e:
                print(f"  failed to add vector column or index: {e}")
                has_pgvector = False
        if not has_pgvector:
            print("  numpy fallback mode — embeddings stored as bytea, ranked in Python")

    print("Done.")


if __name__ == "__main__":
    main()
