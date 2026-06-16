"""Memory routes — observability + management of the shared memory."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from app.auth.deps import get_company_context, CompanyContext
from app.memory import store as memory


router = APIRouter(prefix="/api/memory", tags=["memory"])


class RetrieveRequest(BaseModel):
    query: str
    k: int = Field(default=5, ge=1, le=20)
    kinds: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    min_score: float = Field(default=0.45, ge=0.0, le=1.0)


@router.get("/stats")
def stats(ctx: CompanyContext = Depends(get_company_context)):
    return memory.stats(ctx.company_id)


@router.get("/recent")
def recent(limit: int = Query(default=50, ge=1, le=500),
           kind: Optional[str] = None,
           ctx: CompanyContext = Depends(get_company_context)):
    kinds = [kind] if kind else None
    rows = memory.list_recent(ctx.company_id, limit=limit, kinds=kinds)
    return [r.__dict__ for r in rows]


@router.post("/retrieve")
def retrieve(payload: RetrieveRequest,
             ctx: CompanyContext = Depends(get_company_context)):
    rows = memory.retrieve(
        ctx.company_id, query=payload.query, k=payload.k,
        kinds=tuple(payload.kinds) if payload.kinds else None,
        tags=tuple(payload.tags) if payload.tags else None,
        min_score=payload.min_score,
    )
    return [r.__dict__ for r in rows]


@router.delete("/{memory_id}")
def remove(memory_id: int,
           ctx: CompanyContext = Depends(get_company_context)):
    ok = memory.delete(ctx.company_id, memory_id)
    if not ok:
        raise HTTPException(404, "memory not found")
    return {"ok": True}


class ImportanceRequest(BaseModel):
    importance: float = Field(ge=0.0, le=1.0)


@router.put("/{memory_id}/importance")
def set_importance(memory_id: int, payload: ImportanceRequest,
                   ctx: CompanyContext = Depends(get_company_context)):
    ok = memory.update_importance(ctx.company_id, memory_id, payload.importance)
    if not ok:
        raise HTTPException(404, "memory not found")
    return {"ok": True}
