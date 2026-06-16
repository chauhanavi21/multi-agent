"""Competitor reels data source.

Three modes:
  1. Apify (when APIFY_TOKEN is set) — calls the instagram-scraper actor
     and ingests results into competitor_reels.
  2. Mock — pre-seeded competitor_reels rows the user added manually.
  3. Read-only — fetch_top_reels just queries the table without scraping.

The CMO agent doesn't care about the source: it always calls
get_top_reels(company_id, ...) which returns whatever is freshest in the table.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Iterable

from app.config import settings
from app.db.models import SessionLocal

log = logging.getLogger(__name__)


def _has_apify_config() -> bool:
    return bool(settings.apify_token)


def scrape_competitor_reels(company_id: int, handles: Iterable[str],
                             platform: str = "instagram",
                             max_per_handle: int = 5) -> dict:
    """Pull reels for the listed handles. Returns counts + a few sample rows.

    Best-effort: if Apify isn't configured, we don't scrape; instead we report
    that fact and return whatever's already in the table for these handles.
    """
    from app.db.migrate_phase6 import CompetitorReel
    handles = list(handles)
    db = SessionLocal()
    inserted = 0
    sample = []
    try:
        if _has_apify_config():
            try:
                from apify_client import ApifyClient
                client = ApifyClient(settings.apify_token)
                actor_input = {
                    "directUrls": [f"https://www.instagram.com/{h.lstrip('@')}/reels/"
                                    for h in handles],
                    "resultsType": "posts",
                    "resultsLimit": max_per_handle,
                }
                run = client.actor(settings.apify_instagram_actor).call(run_input=actor_input)
                for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                    if item.get("type") not in (None, "Video", "Reel"):
                        continue
                    handle = item.get("ownerUsername") or "unknown"
                    row = CompetitorReel(
                        company_id=company_id,
                        platform=platform,
                        competitor_handle=handle,
                        url=item.get("url"),
                        caption=(item.get("caption") or "")[:2000],
                        views=int(item.get("videoViewCount") or 0),
                        likes=int(item.get("likesCount") or 0),
                        comments_count=int(item.get("commentsCount") or 0),
                        posted_at=_parse_dt(item.get("timestamp")),
                        source="apify",
                    )
                    db.add(row); inserted += 1
                db.commit()
                log.info("apify scrape inserted %d reels", inserted)
            except Exception as e:
                db.rollback()
                log.warning("apify scrape failed: %s", e)
                # fall through to mock-mode response

        rows = db.query(CompetitorReel).filter(
            CompetitorReel.company_id == company_id,
            CompetitorReel.competitor_handle.in_(handles),
        ).order_by(CompetitorReel.views.desc().nulls_last()).limit(10).all()
        sample = [_to_dict(r) for r in rows[:5]]

        return {
            "inserted": inserted,
            "source": "apify" if _has_apify_config() else "mock",
            "total_for_handles": len(rows),
            "sample": sample,
            "note": None if _has_apify_config() else
                    "APIFY_TOKEN not set — used existing rows; add seed data via API or DB",
        }
    finally:
        db.close()


def get_top_reels(company_id: int, platform: str = "instagram",
                  limit: int = 3, max_age_days: int = 7) -> list[dict]:
    """Return the top reels by views for this company within max_age_days."""
    from app.db.migrate_phase6 import CompetitorReel
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=max_age_days)
        rows = db.query(CompetitorReel).filter(
            CompetitorReel.company_id == company_id,
            CompetitorReel.platform == platform,
            CompetitorReel.fetched_at >= since,
        ).order_by(CompetitorReel.views.desc().nulls_last()).limit(limit).all()
        return [_to_dict(r) for r in rows]
    finally:
        db.close()


def seed_mock_reel(company_id: int, handle: str, platform: str,
                   url: str, caption: str, views: int, likes: int,
                   comments_count: int) -> int:
    """Helper for tests / manual seeding."""
    from app.db.migrate_phase6 import CompetitorReel
    db = SessionLocal()
    try:
        row = CompetitorReel(
            company_id=company_id, platform=platform,
            competitor_handle=handle, url=url,
            caption=caption, views=views, likes=likes,
            comments_count=comments_count,
            posted_at=datetime.utcnow(),
            source="mock",
        )
        db.add(row); db.commit(); db.refresh(row)
        return row.id
    finally:
        db.close()


def _to_dict(r) -> dict:
    return {
        "id": r.id, "platform": r.platform, "handle": r.competitor_handle,
        "url": r.url, "caption": r.caption,
        "views": r.views, "likes": r.likes, "comments_count": r.comments_count,
        "posted_at": r.posted_at.isoformat() if r.posted_at else None,
        "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
        "source": r.source,
    }


def _parse_dt(s) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
