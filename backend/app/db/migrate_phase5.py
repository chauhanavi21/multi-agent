"""Phase 5 migration.

Adds `cloud_provider` column to companies. Values: 'anthropic' or 'bedrock'.

Why: per-company override for which Claude provider to call when a quality/
premium tier runs. Local tiers always hit Ollama regardless.

Run: python -m app.db.migrate_phase5
"""
from sqlalchemy import text
from app.db.models import engine
# Import Phase 3 so SQLAlchemy knows about companies (defensive)
from app.db import migrate_phase3  # noqa: F401


ALTER_SQL = [
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS cloud_provider VARCHAR(20) "
    "DEFAULT 'anthropic' NOT NULL",
]


def main():
    print("Adding companies.cloud_provider...")
    with engine.begin() as conn:
        for stmt in ALTER_SQL:
            conn.execute(text(stmt))
    print("Done.")


if __name__ == "__main__":
    main()
