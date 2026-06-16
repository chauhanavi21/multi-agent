"""APScheduler runner.

Lifecycle: started by main.py via @app.on_event('startup'), stopped on shutdown.

Per-company per-job schedule is stored in scheduler_jobs. When the scheduler
starts (and once a minute via a tick job), it reconciles APScheduler's view of
the world with the DB:
  - DB row enabled + company.scheduler_enabled  -> APScheduler job exists with that cron
  - otherwise -> no APScheduler job

The reconcile loop also handles: per-company defaults (if no rows exist for a
freshly-toggled-on company, seed the 4 defaults).
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.scheduler.jobs import JOB_REGISTRY, DEFAULT_CRONS

log = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


def _job_id(company_id: int, job_name: str) -> str:
    return f"c{company_id}:{job_name}"


async def _execute(company_id: int, job_name: str):
    """Wrapper around the actual job function — updates last_run_at + status."""
    from app.db.models import SessionLocal
    from app.db.migrate_phase6 import SchedulerJob

    fn = JOB_REGISTRY.get(job_name)
    if not fn:
        log.warning("no handler for job_name=%s", job_name)
        return

    log.info("running scheduled job c=%d job=%s", company_id, job_name)
    res = {}
    try:
        res = await fn(company_id)
    except Exception as e:
        res = {"ok": False, "error": str(e)}

    db = SessionLocal()
    try:
        row = db.query(SchedulerJob).filter(
            SchedulerJob.company_id == company_id,
            SchedulerJob.job_name == job_name,
        ).first()
        if row:
            row.last_run_at = datetime.utcnow()
            row.last_status = "ok" if res.get("ok") else "error"
            row.last_error = (res.get("error") or "")[:1000] if not res.get("ok") else None
            db.commit()
    finally:
        db.close()


def _seed_defaults_if_missing(db, company_id: int):
    """Insert default job rows for a company if it has none yet."""
    from app.db.migrate_phase6 import SchedulerJob
    existing = {r.job_name for r in db.query(SchedulerJob).filter(
        SchedulerJob.company_id == company_id
    ).all()}
    for name, cron in DEFAULT_CRONS.items():
        if name not in existing:
            db.add(SchedulerJob(
                company_id=company_id, job_name=name,
                cron_expr=cron, enabled=True,
            ))
    db.commit()


def _reconcile():
    """Sync APScheduler's job list with the DB."""
    if _scheduler is None:
        return
    from app.db.models import SessionLocal
    from app.db.migrate_phase3 import Company
    from app.db.migrate_phase6 import SchedulerJob
    from app.db import model_extensions_p6  # noqa: F401

    db = SessionLocal()
    try:
        # For every company with scheduler_enabled, ensure defaults exist
        companies = db.query(Company).filter(
            Company.scheduler_enabled == True   # noqa: E712
        ).all()
        for c in companies:
            _seed_defaults_if_missing(db, c.id)

        # Now load the full job list
        rows = db.query(SchedulerJob).join(
            Company, SchedulerJob.company_id == Company.id
        ).all()

        # Map: what should be scheduled
        wanted = {}
        for r in rows:
            company = db.query(Company).filter(Company.id == r.company_id).first()
            if not company or not company.scheduler_enabled or not r.enabled:
                continue
            wanted[_job_id(r.company_id, r.job_name)] = (r.company_id, r.job_name, r.cron_expr)

        # Remove obsolete jobs
        for j in _scheduler.get_jobs():
            if j.id not in wanted:
                try:
                    _scheduler.remove_job(j.id)
                except Exception:
                    pass

        # Add / update wanted jobs
        for jid, (cid, name, cron_expr) in wanted.items():
            try:
                trigger = CronTrigger.from_crontab(cron_expr)
            except Exception as e:
                log.warning("bad cron '%s' for %s: %s", cron_expr, jid, e)
                continue
            existing = _scheduler.get_job(jid)
            if existing:
                existing.reschedule(trigger=trigger)
            else:
                _scheduler.add_job(
                    _execute, trigger=trigger,
                    args=[cid, name], id=jid,
                    replace_existing=True, max_instances=1, coalesce=True,
                )
    finally:
        db.close()


def start():
    global _scheduler
    if settings.scheduler_mode == "disabled":
        log.info("scheduler disabled by config")
        return
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    log.info("scheduler started (mode=%s)", settings.scheduler_mode)
    # Tick every minute to pick up DB changes
    _scheduler.add_job(_reconcile, trigger=CronTrigger.from_crontab("* * * * *"),
                       id="__reconcile__", max_instances=1, coalesce=True)
    _reconcile()


def stop():
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    log.info("scheduler stopped")


def list_active_jobs() -> list[dict]:
    if _scheduler is None:
        return []
    return [
        {"id": j.id, "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None}
        for j in _scheduler.get_jobs()
    ]


async def run_job_now(company_id: int, job_name: str) -> dict:
    fn = JOB_REGISTRY.get(job_name)
    if not fn:
        return {"ok": False, "error": f"unknown job: {job_name}"}
    return await _execute(company_id, job_name) or {"ok": True, "note": "started"}
