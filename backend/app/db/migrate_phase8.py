"""Phase 8 — Stripe billing columns + terms acceptance audit.

Run: python -m app.db.migrate_phase8
"""
from sqlalchemy import text
from app.db.models import engine
from app.db import migrate_phase3  # noqa: F401

ALTER_SQL = [
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(80)",
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(80)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMP WITH TIME ZONE",
]


def main():
    print("Adding Stripe + terms acceptance columns...")
    with engine.begin() as conn:
        for stmt in ALTER_SQL:
            conn.execute(text(stmt))
    print("Done.")


if __name__ == "__main__":
    main()
