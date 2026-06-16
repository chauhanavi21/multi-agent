"""FastAPI app — Phase 6.

New in Phase 6:
- Scheduler lifecycle (startup/shutdown hooks)
- Memory routes
- Scheduler management routes
- Daily plan endpoint
- Reel scripts endpoint
- SMS outbox endpoint
- Lead pipeline endpoints (qualify, transition, history)
"""
import json
import asyncio
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import model_extensions       # noqa: F401
from app.db import model_extensions_p4    # noqa: F401
from app.db import model_extensions_p5    # noqa: F401
from app.db import model_extensions_p6    # noqa: F401
from app.db import model_extensions_p7    # noqa: F401
from app.db import model_extensions_p8    # noqa: F401
from app.db.models import get_db, Lead
from app.db.migrate_phase2 import ChatSession, AgentMessage
from app.tools import lead_tools, email_tools, crm_tools, task_queue, lead_pipeline, sms_tools
from app.agents.sales_agent import run_agent
from app.agents.manager import run_manager
from app.agents import registry

from app.auth.deps import get_current_user, get_company_context, CompanyContext
from app.db.migrate_phase3 import User
from app.routes import auth_routes, company_routes, admin_routes
from app.routes import observability_routes, memory_routes, scheduler_routes, billing_routes
from app.scheduler import runner as sched_runner
from app.billing.plans import get_company_plan
from app.billing.limits import check_chat_allowed


@asynccontextmanager
async def lifespan(app: FastAPI):
    sched_runner.start()
    yield
    sched_runner.stop()


app = FastAPI(title="Sales Agent API", version="0.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(company_routes.router)
app.include_router(admin_routes.router)
app.include_router(observability_routes.router)
app.include_router(memory_routes.router)
app.include_router(scheduler_routes.router)
app.include_router(billing_routes.router)


class DraftEmailRequest(BaseModel): lead_id: int
class GenerateLeadsRequest(BaseModel): criteria: str
class UpdateDraftRequest(BaseModel):
    subject: str; body: str
class StatusUpdateRequest(BaseModel): status: str
class ChatStartRequest(BaseModel): title: Optional[str] = None
class ChatMessageRequest(BaseModel):
    session_id: int; message: str
class QualifyLeadRequest(BaseModel): pass
class TransitionStageRequest(BaseModel):
    to_stage: str
    reason: Optional[str] = None


@app.get("/api/leads")
def list_leads(criteria: Optional[str] = None,
               ctx: CompanyContext = Depends(get_company_context),
               db: Session = Depends(get_db)):
    rows = lead_tools.search_leads(db, ctx.company_id, criteria=criteria, limit=50)
    # Hydrate pipeline columns
    if rows:
        ids = [r["id"] for r in rows]
        m = {l.id: l for l in db.query(Lead).filter(Lead.id.in_(ids)).all()}
        for r in rows:
            l = m.get(r["id"])
            if l:
                r["icp_score"] = getattr(l, "icp_score", None)
                r["current_stage"] = getattr(l, "current_stage", None)
                r["last_contacted_at"] = (l.last_contacted_at.isoformat()
                                           if getattr(l, "last_contacted_at", None) else None)
                r["next_followup_at"] = (l.next_followup_at.isoformat()
                                          if getattr(l, "next_followup_at", None) else None)
    return rows


@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: int,
             ctx: CompanyContext = Depends(get_company_context),
             db: Session = Depends(get_db)):
    lead = lead_tools.get_lead(db, ctx.company_id, lead_id)
    if not lead: raise HTTPException(404, "lead not found")
    l = db.query(Lead).filter(Lead.id == lead_id).first()
    if l:
        lead["icp_score"] = getattr(l, "icp_score", None)
        lead["current_stage"] = getattr(l, "current_stage", None)
    return lead


@app.put("/api/leads/{lead_id}/status")
def set_status(lead_id: int, payload: StatusUpdateRequest,
               ctx: CompanyContext = Depends(get_company_context),
               db: Session = Depends(get_db)):
    r = crm_tools.log_followup(db, ctx.company_id, lead_id, payload.status)
    if not r["ok"]: raise HTTPException(400, r.get("error", "failed"))
    return r


@app.get("/api/leads/{lead_id}/drafts")
def list_drafts(lead_id: int,
                ctx: CompanyContext = Depends(get_company_context),
                db: Session = Depends(get_db)):
    return email_tools.list_drafts(db, ctx.company_id, lead_id)


@app.get("/api/leads/{lead_id}/stage_history")
def lead_stage_history(lead_id: int,
                        ctx: CompanyContext = Depends(get_company_context)):
    return lead_pipeline.stage_history(ctx.company_id, lead_id)


@app.put("/api/drafts/{draft_id}")
def update_draft(draft_id: int, payload: UpdateDraftRequest,
                 ctx: CompanyContext = Depends(get_company_context),
                 db: Session = Depends(get_db)):
    r = email_tools.update_draft(db, ctx.company_id, draft_id, payload.subject, payload.body)
    if r is None: raise HTTPException(404, "draft not found")
    return {"ok": True, "draft_id": r}


@app.post("/api/drafts/{draft_id}/send")
def send_draft(draft_id: int,
               ctx: CompanyContext = Depends(get_company_context),
               db: Session = Depends(get_db)):
    r = email_tools.send_email(db, ctx.company_id, draft_id)
    if not r["ok"]: raise HTTPException(400, r.get("error", "failed"))
    return r


def _sse_from_sync_gen(gen):
    async def stream():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def produce():
            try:
                for ev in gen():
                    asyncio.run_coroutine_threadsafe(queue.put(ev), loop)
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    queue.put({"type": "error", "content": str(e)}), loop)
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        loop.run_in_executor(None, produce)
        while True:
            ev = await queue.get()
            if ev is None: break
            yield {"event": "message", "data": json.dumps(ev, default=str)}

    return EventSourceResponse(stream())


@app.post("/api/agents/sales/draft_email")
async def agent_draft_email(payload: DraftEmailRequest,
                             ctx: CompanyContext = Depends(get_company_context)):
    cid = ctx.company_id
    return _sse_from_sync_gen(lambda: run_agent("draft_email", company_id=cid, lead_id=payload.lead_id))


@app.post("/api/agents/sales/generate_leads")
async def agent_generate_leads(payload: GenerateLeadsRequest,
                                ctx: CompanyContext = Depends(get_company_context)):
    cid = ctx.company_id
    return _sse_from_sync_gen(lambda: run_agent("generate_leads", company_id=cid, criteria=payload.criteria))


@app.post("/api/agents/sales/qualify_lead/{lead_id}")
async def qualify_lead(lead_id: int,
                       ctx: CompanyContext = Depends(get_company_context)):
    """Run the LLM ICP qualification for one lead and return the result."""
    from app.agents.sales_agent import SalesWorker
    from app.cost import tracing

    worker = SalesWorker()
    tracing.set_context(tracing.TraceContext(
        company_id=ctx.company_id, agent_name="sales"))
    try:
        final = None
        async for ev in worker.run("qualify_lead",
                                     {"company_id": ctx.company_id, "lead_id": lead_id},
                                     task_id="ad-hoc"):
            if ev.type == "done": final = ev.content
            if ev.type == "error":
                raise HTTPException(400, str(ev.content))
        return final
    finally:
        tracing.set_context(None)


@app.post("/api/agents/sales/transition_stage/{lead_id}")
async def transition_stage(lead_id: int, payload: TransitionStageRequest,
                            ctx: CompanyContext = Depends(get_company_context)):
    res = lead_pipeline.transition(ctx.company_id, lead_id,
                                     to_stage=payload.to_stage,
                                     reason=payload.reason, agent="manual")
    if not res["ok"]: raise HTTPException(400, res.get("error", "failed"))
    return res


@app.get("/api/daily_plan")
def get_daily_plan(plan_date: Optional[str] = None,
                   ctx: CompanyContext = Depends(get_company_context),
                   db: Session = Depends(get_db)):
    from datetime import date
    from app.db.migrate_phase6 import DailyPlan
    pd = plan_date or date.today().isoformat()
    row = db.query(DailyPlan).filter(
        DailyPlan.company_id == ctx.company_id,
        DailyPlan.plan_date == pd,
    ).first()
    if not row:
        return None
    return {
        "id": row.id, "plan_date": row.plan_date,
        "summary": row.summary, "priorities": row.priorities,
        "metrics_yesterday": row.metrics_yesterday,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@app.get("/api/reel_scripts")
def list_reel_scripts(limit: int = 20,
                       ctx: CompanyContext = Depends(get_company_context),
                       db: Session = Depends(get_db)):
    from app.db.migrate_phase6 import ReelScript
    rows = db.query(ReelScript).filter(
        ReelScript.company_id == ctx.company_id
    ).order_by(ReelScript.id.desc()).limit(min(limit, 100)).all()
    return [
        {"id": r.id, "title": r.title, "hook": r.hook,
         "body": r.body, "cta": r.cta,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]


@app.get("/api/sms")
def list_sms(limit: int = 50,
             ctx: CompanyContext = Depends(get_company_context)):
    return sms_tools.list_sms(ctx.company_id, limit=limit)


@app.get("/api/health")
def health():
    return {
        "ok": True, "model": settings.ollama_model, "phase": 6,
        "anthropic_configured": bool(settings.anthropic_api_key),
        "bedrock_region": settings.bedrock_region,
        "twilio_configured": bool(settings.twilio_account_sid
                                   and settings.twilio_auth_token
                                   and settings.twilio_from_number),
        "apify_configured": bool(settings.apify_token),
        "scheduler_mode": settings.scheduler_mode,
    }


@app.get("/api/team")
def team_legacy_endpoint():
    return {"agents": registry.org_chart()}


@app.post("/api/chat/sessions")
def create_chat_session(payload: ChatStartRequest,
                        ctx: CompanyContext = Depends(get_company_context),
                        db: Session = Depends(get_db)):
    s = ChatSession(title=payload.title or "New conversation",
                    user_id=ctx.user.id, company_id=ctx.company_id)
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()}


@app.get("/api/chat/sessions")
def list_chat_sessions(ctx: CompanyContext = Depends(get_company_context),
                       db: Session = Depends(get_db)):
    rows = db.query(ChatSession).filter(
        ChatSession.company_id == ctx.company_id
    ).order_by(ChatSession.id.desc()).limit(50).all()
    return [{"id": r.id, "title": r.title,
             "created_at": r.created_at.isoformat()} for r in rows]


def _verify_session_in_company(db, session_id, company_id):
    return db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.company_id == company_id
    ).first() is not None


@app.get("/api/chat/sessions/{session_id}/messages")
def get_messages(session_id: int,
                 ctx: CompanyContext = Depends(get_company_context),
                 db: Session = Depends(get_db)):
    if not _verify_session_in_company(db, session_id, ctx.company_id):
        raise HTTPException(404, "session not found")
    msgs = db.query(AgentMessage).filter(
        AgentMessage.session_id == session_id
    ).order_by(AgentMessage.id).all()
    return [{"id": m.id, "role": m.role, "agent_name": m.agent_name,
             "content": m.content, "metadata": m.metadata_json,
             "created_at": m.created_at.isoformat()} for m in msgs]


@app.get("/api/chat/sessions/{session_id}/tasks")
def get_tasks(session_id: int,
              ctx: CompanyContext = Depends(get_company_context),
              db: Session = Depends(get_db)):
    if not _verify_session_in_company(db, session_id, ctx.company_id):
        raise HTTPException(404, "session not found")
    return task_queue.list_tasks_for_session(db, session_id)


@app.post("/api/chat/message")
async def chat_message(payload: ChatMessageRequest,
                       ctx: CompanyContext = Depends(get_company_context),
                       db: Session = Depends(get_db)):
    if not _verify_session_in_company(db, payload.session_id, ctx.company_id):
        raise HTTPException(404, "session not found")
    plan = get_company_plan(db, ctx.company_id)
    check_chat_allowed(ctx.company_id, plan)
    company_id = ctx.company_id
    user_id = ctx.user.id

    async def stream():
        try:
            async for ev in run_manager(payload.session_id, payload.message,
                                         company_id=company_id, user_id=user_id):
                yield {"event": "message", "data": json.dumps(ev, default=str)}
        except Exception as e:
            yield {"event": "message", "data": json.dumps(
                {"type": "error", "agent": "manager", "content": str(e)})}

    return EventSourceResponse(stream())
