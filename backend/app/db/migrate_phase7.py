"""Phase 7 migration — subscription plan on companies.

Adds `plan` column: 'free' | 'pro' | 'team'. Drives which LLM tiers are allowed
and default cloud budget. See app.billing.plans.

Run: python -m app.db.migrate_phase7
"""
from sqlalchemy import text
from app.db.models import engine
from app.db import migrate_phase3  # noqa: F401


ALTER_SQL = [
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS plan VARCHAR(20) "
    "DEFAULT 'free' NOT NULL",
]


def main():
    print("Adding companies.plan...")
    with engine.begin() as conn:
        for stmt in ALTER_SQL:
            conn.execute(text(stmt))
    print("Done.")


if __name__ == "__main__":
    main()
