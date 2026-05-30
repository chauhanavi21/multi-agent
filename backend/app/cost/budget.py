"""Per-company monthly budget enforcement.

Algorithm:
  - Sum usage_records.cost_usd for current calendar month, scoped to company.
  - Compare to companies.monthly_budget_usd.
  - Return BudgetStatus(spent, budget, pct_used, can_use_cloud, must_downgrade).

The router consults this before every cloud-tier call. Local tier is unlimited.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings


@dataclass
class BudgetStatus:
    company_id: int
    spent_usd: float
    budget_usd: float
    pct_used: float
    can_use_cloud: bool       # False if cloud is disabled OR over hard limit
    must_downgrade: bool      # True if over soft limit (still allowed, but should fallback)


def _month_start_utc() -> datetime:
    n = datetime.now(timezone.utc)
    return datetime(n.year, n.month, 1, tzinfo=timezone.utc)


def get_status(db: Session, company_id: int) -> BudgetStatus:
    """Compute the current budget status for a company. Imports done lazily
    so this module doesn't create circular imports during migration."""
    from app.db.migrate_phase3 import Company
    from app.db import model_extensions_p4  # noqa: F401 ensure ORM has new columns
    from app.db.migrate_phase4 import UsageRecord

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return BudgetStatus(
            company_id=company_id, spent_usd=0.0, budget_usd=0.0,
            pct_used=0.0, can_use_cloud=False, must_downgrade=True,
        )

    budget = float(company.monthly_budget_usd or settings.default_monthly_budget_usd)
    use_cloud = bool(company.use_cloud_api)

    spent = db.query(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0)).filter(
        UsageRecord.company_id == company_id,
        UsageRecord.created_at >= _month_start_utc(),
    ).scalar() or 0.0
    spent = float(spent)

    pct = (spent / budget * 100.0) if budget > 0 else 100.0
    must_downgrade = pct >= settings.budget_soft_limit_pct
    over_hard = pct >= settings.budget_hard_limit_pct
    can_use_cloud = use_cloud and not over_hard

    return BudgetStatus(
        company_id=company_id, spent_usd=round(spent, 6),
        budget_usd=budget, pct_used=round(pct, 2),
        can_use_cloud=can_use_cloud, must_downgrade=must_downgrade,
    )


def record_usage(db: Session, company_id: int, model: str, input_tokens: int,
                 output_tokens: int, cost_usd: float, agent_name: str | None,
                 trace_span_id: int | None = None, was_cache_hit: bool = False):
    """Write one usage_record row. Caller commits."""
    from app.db.migrate_phase4 import UsageRecord
    row = UsageRecord(
        company_id=company_id, model=model,
        input_tokens=input_tokens, output_tokens=output_tokens,
        cost_usd=cost_usd, agent_name=agent_name,
        trace_span_id=trace_span_id, was_cache_hit=was_cache_hit,
    )
    db.add(row)
    db.commit()
    return row.id
