"""FastAPI app — Phase 3.

All Phase 1 + Phase 2 endpoints now require authentication and are
company-scoped via the get_company_context dependency.
"""
import json
import asyncio
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import model_extensions  # noqa: F401 — augments Phase 1 models with company_id
from app.db.models import get_db
from app.db.migrate_phase2 import ChatSession, AgentMessage
from app.tools import lead_tools, email_tools, crm_tools, task_queue
from app.agents.sales_agent import run_agent
from app.agents.manager import run_manager
from app.agents import registry

from app.auth.deps import get_current_user, get_company_context, CompanyContext
from app.db.migrate_phase3 import User
from app.routes import auth_routes, company_routes, admin_routes


app = FastAPI(title="Sales Agent API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount auth + company + admin routers
app.include_router(auth_routes.router)
app.include_router(company_routes.router)
app.include_router(admin_routes.router)


# ===== request/response models =====

class DraftEmailRequest(BaseModel):
    lead_id: int


class GenerateLeadsRequest(BaseModel):
    criteria: str


class UpdateDraftRequest(BaseModel):
    subject: str
    body: str


class StatusUpdateRequest(BaseModel):
    status: str


class ChatStartRequest(BaseModel):
    title: Optional[str] = None


class ChatMessageRequest(BaseModel):
    session_id: int
    message: str


# ===== Phase 1 routes — now company-scoped =====

@app.get("/api/leads")
def list_leads(criteria: Optional[str] = None,
               ctx: CompanyContext = Depends(get_company_context),
               db: Session = Depends(get_db)):
    return lead_tools.search_leads(db, ctx.company_id, criteria=criteria, limit=50)


@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: int,
             ctx: CompanyContext = Depends(get_company_context),
             db: Session = Depends(get_db)):
    lead = lead_tools.get_lead(db, ctx.company_id, lead_id)
    if not lead:
        raise HTTPException(404, "lead not found")
    return lead


@app.put("/api/leads/{lead_id}/status")
def set_status(lead_id: int, payload: StatusUpdateRequest,
               ctx: CompanyContext = Depends(get_company_context),
               db: Session = Depends(get_db)):
    r = crm_tools.log_followup(db, ctx.company_id, lead_id, payload.status)
    if not r["ok"]:
        raise HTTPException(400, r.get("error", "failed"))
    return r


@app.get("/api/leads/{lead_id}/drafts")
def list_drafts(lead_id: int,
                ctx: CompanyContext = Depends(get_company_context),
                db: Session = Depends(get_db)):
    return email_tools.list_drafts(db, ctx.company_id, lead_id)


@app.put("/api/drafts/{draft_id}")
def update_draft(draft_id: int, payload: UpdateDraftRequest,
                 ctx: CompanyContext = Depends(get_company_context),
                 db: Session = Depends(get_db)):
    r = email_tools.update_draft(db, ctx.company_id, draft_id, payload.subject, payload.body)
    if r is None:
        raise HTTPException(404, "draft not found")
    return {"ok": True, "draft_id": r}


@app.post("/api/drafts/{draft_id}/send")
def send_draft(draft_id: int,
               ctx: CompanyContext = Depends(get_company_context),
               db: Session = Depends(get_db)):
    r = email_tools.send_email(db, ctx.company_id, draft_id)
    if not r["ok"]:
        raise HTTPException(400, r.get("error", "failed"))
    return r


def _sse_from_sync_gen(gen):
    """Bridge a sync generator into an SSE response."""
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
                    queue.put({"type": "error", "content": str(e)}), loop
                )
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        loop.run_in_executor(None, produce)
        while True:
            ev = await queue.get()
            if ev is None:
                break
            yield {"event": "message", "data": json.dumps(ev, default=str)}

    return EventSourceResponse(stream())


@app.post("/api/agents/sales/draft_email")
async def agent_draft_email(payload: DraftEmailRequest,
                             ctx: CompanyContext = Depends(get_company_context)):
    cid = ctx.company_id
    return _sse_from_sync_gen(
        lambda: run_agent("draft_email", company_id=cid, lead_id=payload.lead_id)
    )


@app.post("/api/agents/sales/generate_leads")
async def agent_generate_leads(payload: GenerateLeadsRequest,
                                ctx: CompanyContext = Depends(get_company_context)):
    cid = ctx.company_id
    return _sse_from_sync_gen(
        lambda: run_agent("generate_leads", company_id=cid, criteria=payload.criteria)
    )


@app.get("/api/health")
def health():
    return {"ok": True, "model": settings.ollama_model, "phase": 3}


# ===== Phase 2 routes — now company-scoped =====

@app.get("/api/team")
def team_legacy_endpoint():
    """Public org chart info — anyone can see what agents exist."""
    return {"agents": registry.org_chart()}


@app.post("/api/chat/sessions")
def create_chat_session(payload: ChatStartRequest,
                        ctx: CompanyContext = Depends(get_company_context),
                        db: Session = Depends(get_db)):
    s = ChatSession(title=payload.title or "New conversation",
                    user_id=ctx.user.id, company_id=ctx.company_id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()}


@app.get("/api/chat/sessions")
def list_chat_sessions(ctx: CompanyContext = Depends(get_company_context),
                       db: Session = Depends(get_db)):
    rows = db.query(ChatSession).filter(
        ChatSession.company_id == ctx.company_id
    ).order_by(ChatSession.id.desc()).limit(50).all()
    return [
        {"id": r.id, "title": r.title, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


def _verify_session_in_company(db: Session, session_id: int, company_id: int) -> bool:
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
    return [
        {
            "id": m.id, "role": m.role, "agent_name": m.agent_name,
            "content": m.content, "metadata": m.metadata_json,
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ]


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
    """Stream a manager turn over SSE — company-scoped."""
    if not _verify_session_in_company(db, payload.session_id, ctx.company_id):
        raise HTTPException(404, "session not found")
    company_id = ctx.company_id
    user_id = ctx.user.id

    async def stream():
        try:
            async for ev in run_manager(payload.session_id, payload.message,
                                         company_id=company_id, user_id=user_id):
                yield {"event": "message", "data": json.dumps(ev, default=str)}
        except Exception as e:
            yield {"event": "message", "data": json.dumps(
                {"type": "error", "agent": "manager", "content": str(e)}
            )}

    return EventSourceResponse(stream())
