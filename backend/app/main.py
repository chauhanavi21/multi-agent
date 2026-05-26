import json
import asyncio
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import get_db
from app.db.migrate_phase2 import ChatSession, AgentMessage
from app.tools import lead_tools, email_tools, crm_tools, task_queue
from app.agents.sales_agent import run_agent           # Phase 1 compat
from app.agents.manager import run_manager             # Phase 2
from app.agents import registry


app = FastAPI(title="Sales Agent API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# ===== Phase 1 routes (unchanged) =====

@app.get("/api/leads")
def list_leads(criteria: Optional[str] = None, db: Session = Depends(get_db)):
    return lead_tools.search_leads(db, criteria=criteria, limit=50)


@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = lead_tools.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "lead not found")
    return lead


@app.put("/api/leads/{lead_id}/status")
def set_status(lead_id: int, payload: StatusUpdateRequest, db: Session = Depends(get_db)):
    r = crm_tools.log_followup(db, lead_id, payload.status)
    if not r["ok"]:
        raise HTTPException(400, r.get("error", "failed"))
    return r


@app.get("/api/leads/{lead_id}/drafts")
def list_drafts(lead_id: int, db: Session = Depends(get_db)):
    return email_tools.list_drafts(db, lead_id)


@app.put("/api/drafts/{draft_id}")
def update_draft(draft_id: int, payload: UpdateDraftRequest, db: Session = Depends(get_db)):
    r = email_tools.update_draft(db, draft_id, payload.subject, payload.body)
    if r is None:
        raise HTTPException(404, "draft not found")
    return {"ok": True, "draft_id": r}


@app.post("/api/drafts/{draft_id}/send")
def send_draft(draft_id: int, db: Session = Depends(get_db)):
    r = email_tools.send_email(db, draft_id)
    if not r["ok"]:
        raise HTTPException(400, r.get("error", "failed"))
    return r


def _sse_from_sync_gen(gen):
    """Bridge a sync generator into an SSE response (used by Phase 1 endpoints)."""
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
async def agent_draft_email(payload: DraftEmailRequest):
    return _sse_from_sync_gen(lambda: run_agent("draft_email", lead_id=payload.lead_id))


@app.post("/api/agents/sales/generate_leads")
async def agent_generate_leads(payload: GenerateLeadsRequest):
    return _sse_from_sync_gen(lambda: run_agent("generate_leads", criteria=payload.criteria))


@app.get("/api/health")
def health():
    return {"ok": True, "model": settings.ollama_model, "phase": 2}


# ===== Phase 2 routes =====

@app.get("/api/team")
def team():
    """Org chart — what agents exist."""
    return {"agents": registry.org_chart()}


@app.post("/api/chat/sessions")
def create_chat_session(payload: ChatStartRequest, db: Session = Depends(get_db)):
    s = ChatSession(title=payload.title or "New conversation")
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()}


@app.get("/api/chat/sessions")
def list_chat_sessions(db: Session = Depends(get_db)):
    rows = db.query(ChatSession).order_by(ChatSession.id.desc()).limit(50).all()
    return [
        {"id": r.id, "title": r.title, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@app.get("/api/chat/sessions/{session_id}/messages")
def get_messages(session_id: int, db: Session = Depends(get_db)):
    msgs = db.query(AgentMessage).filter(AgentMessage.session_id == session_id).order_by(AgentMessage.id).all()
    return [
        {
            "id": m.id, "role": m.role, "agent_name": m.agent_name,
            "content": m.content,
            "metadata": m.metadata_json,
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ]


@app.get("/api/chat/sessions/{session_id}/tasks")
def get_tasks(session_id: int, db: Session = Depends(get_db)):
    return task_queue.list_tasks_for_session(db, session_id)


@app.post("/api/chat/message")
async def chat_message(payload: ChatMessageRequest):
    """Stream a manager turn over SSE."""
    async def stream():
        try:
            async for ev in run_manager(payload.session_id, payload.message):
                yield {"event": "message", "data": json.dumps(ev, default=str)}
        except Exception as e:
            yield {"event": "message", "data": json.dumps(
                {"type": "error", "agent": "manager", "content": str(e)}
            )}

    return EventSourceResponse(stream())
