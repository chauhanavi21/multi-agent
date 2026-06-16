"""Per-plan rate limits backed by Redis."""
from __future__ import annotations
import time

from fastapi import HTTPException

from app.config import settings
from app.billing.plans import PlanName, PLANS

# Chat messages per company per UTC hour
CHAT_HOURLY_LIMIT: dict[PlanName, int] = {
    "free": 40,
    "pro": 300,
    "team": 2000,
}


def _hour_bucket() -> int:
    return int(time.time()) // 3600


def _redis():
    import redis
    return redis.from_url(settings.redis_url, decode_responses=True)


def check_chat_allowed(company_id: int, plan: PlanName) -> dict:
    """Increment chat counter; raise 429 if over plan limit. Returns usage stats."""
    limit = CHAT_HOURLY_LIMIT.get(plan, CHAT_HOURLY_LIMIT["free"])
    key = f"ratelimit:chat:{company_id}:{_hour_bucket()}"
    try:
        r = _redis()
        count = int(r.incr(key))
        if count == 1:
            r.expire(key, 3700)
    except Exception:
        # Dev without Redis — don't block local work
        return {"used": 0, "limit": limit, "remaining": limit}

    if count > limit:
        raise HTTPException(
            status_code=429,
            detail=f"Chat limit reached ({limit} messages/hour on {PLANS[plan]['display_name']}). "
                   "Upgrade your plan or try again next hour.",
        )
    return {"used": count, "limit": limit, "remaining": max(0, limit - count)}


def chat_limit_status(company_id: int, plan: PlanName) -> dict:
    """Read-only counter for UI (does not increment)."""
    limit = CHAT_HOURLY_LIMIT.get(plan, CHAT_HOURLY_LIMIT["free"])
    key = f"ratelimit:chat:{company_id}:{_hour_bucket()}"
    try:
        r = _redis()
        used = int(r.get(key) or 0)
    except Exception:
        used = 0
    return {"used": used, "limit": limit, "remaining": max(0, limit - used)}
