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
from app.tools import lead_tools, email_tools, crm_tools
from app.agents.sales_agent import run_agent


app = FastAPI(title="Sales Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----- request/response models -----

class DraftEmailRequest(BaseModel):
    lead_id: int


class GenerateLeadsRequest(BaseModel):
    criteria: str


class UpdateDraftRequest(BaseModel):
    subject: str
    body: str


class StatusUpdateRequest(BaseModel):
    status: str


# ----- routes: leads -----

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


# ----- routes: drafts -----

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


# ----- routes: agent (SSE streams) -----

@app.post("/api/agents/sales/draft_email")
async def agent_draft_email(payload: DraftEmailRequest):
    async def stream():
        # Run sync generator in a thread so we don't block the event loop
        loop = asyncio.get_event_loop()

        def runner():
            return list(run_agent("draft_email", lead_id=payload.lead_id))

        # We yield events as they come by polling the generator in a queue
        queue: asyncio.Queue = asyncio.Queue()

        def produce():
            try:
                for ev in run_agent("draft_email", lead_id=payload.lead_id):
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
            yield {"event": "message", "data": json.dumps(ev)}

    return EventSourceResponse(stream())


@app.post("/api/agents/sales/generate_leads")
async def agent_generate_leads(payload: GenerateLeadsRequest):
    async def stream():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def produce():
            try:
                for ev in run_agent("generate_leads", criteria=payload.criteria):
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
            yield {"event": "message", "data": json.dumps(ev)}

    return EventSourceResponse(stream())


@app.get("/api/health")
def health():
    return {"ok": True, "model": settings.ollama_model}
