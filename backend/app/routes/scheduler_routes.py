"""Scheduler management routes."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.auth.deps import get_company_context, CompanyContext
from app.scheduler import runner as sched
from app.scheduler.jobs import JOB_REGISTRY, DEFAULT_CRONS


router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/jobs")
def list_jobs(ctx: CompanyContext = Depends(get_company_context),
              db: Session = Depends(get_db)):
    from app.db.migrate_phase6 import SchedulerJob
    rows = db.query(SchedulerJob).filter(
        SchedulerJob.company_id == ctx.company_id
    ).order_by(SchedulerJob.job_name).all()

    # If empty, surface the defaults so the UI can show the user what's available
    if not rows:
        return [
            {"job_name": n, "cron_expr": c, "enabled": False,
             "last_run_at": None, "last_status": None, "default": True}
            for n, c in DEFAULT_CRONS.items()
        ]
    return [
        {
            "id": r.id, "job_name": r.job_name, "cron_expr": r.cron_expr,
            "enabled": r.enabled,
            "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
            "last_status": r.last_status, "last_error": r.last_error,
            "default": False,
        }
        for r in rows
    ]


class UpsertJobRequest(BaseModel):
    cron_expr: str = Field(min_length=5, max_length=60)
    enabled: bool = True


@router.put("/jobs/{job_name}")
def upsert_job(job_name: str, payload: UpsertJobRequest,
               ctx: CompanyContext = Depends(get_company_context),
               db: Session = Depends(get_db)):
    if job_name not in JOB_REGISTRY:
        raise HTTPException(400, f"unknown job: {job_name}")
    from app.db.migrate_phase6 import SchedulerJob
    row = db.query(SchedulerJob).filter(
        SchedulerJob.company_id == ctx.company_id,
        SchedulerJob.job_name == job_name,
    ).first()
    if row:
        row.cron_expr = payload.cron_expr
        row.enabled = payload.enabled
    else:
        row = SchedulerJob(
            company_id=ctx.company_id, job_name=job_name,
            cron_expr=payload.cron_expr, enabled=payload.enabled,
        )
        db.add(row)
    db.commit(); db.refresh(row)
    return {"ok": True, "id": row.id, "job_name": row.job_name,
            "cron_expr": row.cron_expr, "enabled": row.enabled}


@router.post("/jobs/{job_name}/run_now")
async def run_now(job_name: str,
                  ctx: CompanyContext = Depends(get_company_context)):
    res = await sched.run_job_now(ctx.company_id, job_name)
    return res or {"ok": True}


@router.get("/active")
def active_jobs(ctx: CompanyContext = Depends(get_company_context)):
    """Returns the runtime-scheduled jobs for this process (debug)."""
    all_jobs = sched.list_active_jobs()
    mine = [j for j in all_jobs if j["id"].startswith(f"c{ctx.company_id}:")]
    return mine
