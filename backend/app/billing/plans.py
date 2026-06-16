"""Subscription plan → cloud permissions and default budgets.

Plans control which LLM tiers a company may use. The router still enforces
monthly_budget_usd on top of this (soft downgrade at 80%, hard block at 100%).

  free  — local Ollama only (cheap + standard)
  pro   — + quality tier (Claude Haiku) with included cloud budget
  team  — + premium tier (Claude Sonnet) with higher cloud budget
"""
from __future__ import annotations
from typing import Literal, TypedDict

from sqlalchemy.orm import Session

Tier = Literal["cheap", "standard", "quality", "premium"]

PlanName = Literal["free", "pro", "team"]


class PlanConfig(TypedDict):
    display_name: str
    monthly_budget_usd: float
    use_cloud_api: bool
    allows_quality: bool
    allows_premium: bool
    suggested_price_usd: int  # documentation only — not charged by this app yet


PLANS: dict[PlanName, PlanConfig] = {
    "free": {
        "display_name": "Free — Local AI",
        "monthly_budget_usd": 0.0,
        "use_cloud_api": False,
        "allows_quality": False,
        "allows_premium": False,
        "suggested_price_usd": 0,
    },
    "pro": {
        "display_name": "Pro",
        "monthly_budget_usd": 8.0,
        "use_cloud_api": True,
        "allows_quality": True,
        "allows_premium": False,
        "suggested_price_usd": 39,
    },
    "team": {
        "display_name": "Team",
        "monthly_budget_usd": 20.0,
        "use_cloud_api": True,
        "allows_quality": True,
        "allows_premium": True,
        "suggested_price_usd": 99,
    },
}


def _normalize_plan(plan: str | None) -> PlanName:
    if plan in PLANS:
        return plan  # type: ignore[return-value]
    return "free"


def get_company_plan(db: Session, company_id: int) -> PlanName:
    from app.db.migrate_phase3 import Company
    from app.db import model_extensions_p7  # noqa: F401
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        return "free"
    return _normalize_plan(getattr(c, "plan", None))


def apply_plan_to_company(company, plan: PlanName) -> None:
    """Set plan column and sync cloud toggle + budget to plan defaults."""
    cfg = PLANS[plan]
    company.plan = plan
    company.use_cloud_api = cfg["use_cloud_api"]
    company.monthly_budget_usd = cfg["monthly_budget_usd"]


def plan_allows_tier(plan: PlanName, tier: Tier) -> bool:
    if tier in ("cheap", "standard"):
        return True
    cfg = PLANS[plan]
    if tier == "quality":
        return cfg["allows_quality"]
    if tier == "premium":
        return cfg["allows_premium"]
    return False


def plan_summary(plan: PlanName) -> dict:
    cfg = PLANS[plan]
    return {
        "plan": plan,
        "display_name": cfg["display_name"],
        "allows_quality": cfg["allows_quality"],
        "allows_premium": cfg["allows_premium"],
        "included_cloud_budget_usd": cfg["monthly_budget_usd"],
        "suggested_price_usd": cfg["suggested_price_usd"],
        "ai_mode": "local_only" if plan == "free" else "local_plus_premium",
    }


def resolve_sales_tier(plan: PlanName, action: str) -> Tier:
    """Pro/Team get Claude-quality email drafts; Free stays on local Llama."""
    if action == "draft_email" and plan in ("pro", "team"):
        return "quality"
    defaults: dict[str, Tier] = {
        "draft_email": "standard",
        "generate_leads": "standard",
        "search_leads": "cheap",
        "qualify_lead": "cheap",
        "transition_stage": "cheap",
        "follow_up_now": "standard",
    }
    return defaults.get(action, "standard")
