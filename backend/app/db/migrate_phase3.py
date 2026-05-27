"""Phase 3 migration.

Creates new tables (users, companies, company_members) and ALTERs existing
tables (leads, email_drafts, chat_sessions) to add a nullable company_id.

Existing rows get company_id=NULL — they remain visible only to admins. New
data goes in the right company. Run a one-time backfill if you want existing
Phase 1+2 data assigned to a company:
    python -m app.db.migrate_phase3 --backfill <company_id>

Run with: python -m app.db.migrate_phase3
"""
import sys
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, text,
)
from sqlalchemy.orm import relationship
from app.db.models import Base, engine, SessionLocal


class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # company-specific org chart override (None = use global template)
    org_chart_override = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    full_name = Column(String(160), default="")
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)


class CompanyMember(Base):
    """For future multi-user-per-company. Owner is also a row here."""
    __tablename__ = "company_members"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    role = Column(String(40), default="owner")    # owner, member
    created_at = Column(DateTime, default=datetime.utcnow)


# ALTER statements for existing tables. Use IF NOT EXISTS so the migration is
# idempotent — safe to re-run.
ALTER_SQL = [
    # Add company_id to existing tables
    'ALTER TABLE leads ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)',
    'ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)',
    'ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id_fk INTEGER REFERENCES users(id)',
    # chat_sessions already had user_id and company_id from Phase 2 — those were nullable plain ints.
    # Now we add proper FKs alongside (Postgres won't let us change an existing column type easily).
    # The existing user_id/company_id columns stay for compat; routes use the new FK-backed columns going forward.
    'ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS company_id_fk INTEGER REFERENCES companies(id)',

    # Indexes for the new filtering
    'CREATE INDEX IF NOT EXISTS ix_leads_company ON leads(company_id)',
    'CREATE INDEX IF NOT EXISTS ix_drafts_company ON email_drafts(company_id)',
    'CREATE INDEX IF NOT EXISTS ix_sessions_company ON chat_sessions(company_id_fk)',
]


def run_migration():
    print("Creating Phase 3 tables (users, companies, company_members)...")
    Base.metadata.create_all(bind=engine, tables=[
        Company.__table__,
        User.__table__,
        CompanyMember.__table__,
    ])

    print("Altering existing tables to add company_id (idempotent)...")
    with engine.begin() as conn:
        for stmt in ALTER_SQL:
            conn.execute(text(stmt))
    print("Done.")


def backfill(company_id: int):
    """Assign all existing NULL-company rows to a given company."""
    print(f"Backfilling existing Phase 1+2 data to company_id={company_id}...")
    with engine.begin() as conn:
        for tbl in ["leads", "email_drafts"]:
            r = conn.execute(text(
                f"UPDATE {tbl} SET company_id = :cid WHERE company_id IS NULL"
            ), {"cid": company_id})
            print(f"  {tbl}: {r.rowcount} rows updated")
        r = conn.execute(text(
            "UPDATE chat_sessions SET company_id_fk = :cid WHERE company_id_fk IS NULL"
        ), {"cid": company_id})
        print(f"  chat_sessions: {r.rowcount} rows updated")


def main():
    run_migration()
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--backfill":
        backfill(int(args[1]))


if __name__ == "__main__":
    main()
