"""Memory store with auto-detect backend.

How the auto-detect works (one-shot at module import):
  - We probe the DB for pgvector by reading pg_extension.
  - If present: queries use ORDER BY embedding_vec <=> $query_vec.
  - If absent: every memory is loaded for the company and ranked in Python
    via numpy cosine similarity.

Either way embeddings are persisted as LargeBinary (np.float32.tobytes) so
the data is portable across backends. The vector column when pgvector is
available is a duplicate, written at insert time alongside the bytes.

Memories aren't raw observations — they're compressed via an LLM into
short, self-contained, specific sentences. This is the difference between
a useful memory store and a graveyard.
"""
from __future__ import annotations
import json
import logging
import numpy as np
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import text, desc
from sqlalchemy.orm import Session

from app.db.models import SessionLocal
from app.cost import cache as cache_mod   # reuse Ollama embed()

log = logging.getLogger(__name__)


# Module-scope state — backend detected once at import time
_BACKEND: str | None = None   # 'pgvector' | 'numpy'


def _detect_backend_once() -> str:
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    db = SessionLocal()
    try:
        row = db.execute(text(
            "SELECT extname FROM pg_extension WHERE extname='vector'"
        )).first()
        _BACKEND = "pgvector" if row else "numpy"
        log.info("memory store backend: %s", _BACKEND)
    except Exception as e:
        log.warning("backend detection failed, defaulting to numpy: %s", e)
        _BACKEND = "numpy"
    finally:
        db.close()
    return _BACKEND


def get_backend_mode() -> str:
    return _detect_backend_once()


# ===== Public dataclass =====
@dataclass
class MemoryRecord:
    id: int
    company_id: int
    kind: str
    content: str
    tags: list
    source_agent: Optional[str]
    source_session_id: Optional[int]
    outcome: Optional[str]
    importance: float
    access_count: int
    last_accessed_at: Optional[str]
    created_at: str
    score: Optional[float] = None   # similarity at retrieval time


def _row_to_record(m, score: Optional[float] = None) -> MemoryRecord:
    return MemoryRecord(
        id=m.id, company_id=m.company_id, kind=m.kind,
        content=m.content, tags=m.tags or [],
        source_agent=m.source_agent, source_session_id=m.source_session_id,
        outcome=m.outcome, importance=float(m.importance or 0.5),
        access_count=int(m.access_count or 0),
        last_accessed_at=m.last_accessed_at.isoformat() if m.last_accessed_at else None,
        created_at=m.created_at.isoformat() if m.created_at else None,
        score=score,
    )


def _embed(text_in: str) -> Optional[np.ndarray]:
    """Reuse the existing embedding helper from the cache module."""
    return cache_mod.embed(text_in)


# ===== Compression =====
async def compress_observation_to_memory(
    raw_observation: str, agent_name: str,
    context_hint: str = "",
) -> dict:
    """Turn a raw agent observation into a compact, useful memory.

    Returns: {"content": "...", "kind": "...", "tags": [...], "importance": 0.5}

    The compression is an LLM call (cheap tier — phi3:mini is enough). It
    enforces: 1-3 sentences, self-contained, specific, no temporary refs.
    """
    from app.cost.router import call_llm
    from app.cost.tracing import get_context

    # If we have no trace context (company_id), fall back to a trivial compression.
    if get_context() is None:
        return {
            "content": raw_observation[:400].strip(),
            "kind": "fact",
            "tags": [agent_name],
            "importance": 0.4,
        }

    system = (
        "You convert raw agent observations into single durable memories. "
        "Rules: 1-3 sentences. Self-contained (don't say 'today' or 'this lead'). "
        "Specific (mention industries, roles, traits, numbers). "
        "Output strictly JSON:\n"
        '{"content":"...","kind":"<lesson|pattern|fact|preference|competitor|win|loss>",'
        '"tags":["..."],"importance":0.0-1.0}\n'
        "If the observation is not worth remembering, output "
        '{"content":"","kind":"fact","tags":[],"importance":0.0}.'
    )
    user_prompt = f"Agent: {agent_name}\nContext: {context_hint or '(none)'}\nObservation:\n{raw_observation}"
    try:
        result = await call_llm(system, user_prompt, tier="cheap",
                                 agent_name=f"{agent_name}+memcompress")
        text_out = result.content.strip()
        # Strip code fences if any
        if text_out.startswith("```"):
            text_out = text_out.strip("`")
            if text_out.lower().startswith("json"):
                text_out = text_out[4:]
            text_out = text_out.strip()
        data = json.loads(text_out)
        # Validate
        if not isinstance(data, dict):
            raise ValueError("not a dict")
        if not data.get("content"):
            return {"content": "", "kind": "fact", "tags": [], "importance": 0.0}
        return {
            "content": str(data["content"])[:600],
            "kind": str(data.get("kind", "fact"))[:40],
            "tags": [str(t)[:40] for t in (data.get("tags") or [])][:8],
            "importance": float(data.get("importance", 0.5)),
        }
    except Exception as e:
        log.warning("memory compression failed (%s); falling back to raw", e)
        return {
            "content": raw_observation[:400].strip(),
            "kind": "fact",
            "tags": [agent_name],
            "importance": 0.4,
        }


# ===== Write =====
def remember(
    company_id: int, kind: str, content: str,
    tags: Sequence[str] = (),
    source_agent: Optional[str] = None,
    source_session_id: Optional[int] = None,
    outcome: Optional[str] = None,
    importance: float = 0.5,
) -> Optional[int]:
    """Write a memory. Returns the id, or None if skipped (e.g., empty content)."""
    content = (content or "").strip()
    if not content:
        return None

    _detect_backend_once()

    vec = _embed(content)
    db = SessionLocal()
    try:
        from app.db.migrate_phase6 import Memory
        m = Memory(
            company_id=company_id, kind=kind[:40], content=content[:2000],
            tags=list(tags)[:8], source_agent=source_agent,
            source_session_id=source_session_id, outcome=outcome,
            importance=max(0.0, min(1.0, importance)),
            embedding_bytes=vec.tobytes() if vec is not None else None,
            embedding_dim=int(vec.size) if vec is not None else None,
        )
        db.add(m); db.commit(); db.refresh(m)

        # Also write the vector column when pgvector is on
        if _BACKEND == "pgvector" and vec is not None:
            try:
                db.execute(text(
                    "UPDATE memories SET embedding_vec = (:v)::vector WHERE id = :id"
                ), {"v": json.dumps(vec.tolist()), "id": m.id})
                db.commit()
            except Exception as e:
                log.warning("pgvector write failed (will fall back to numpy on query): %s", e)
        return m.id
    finally:
        db.close()


# ===== Retrieve =====
def retrieve(
    company_id: int, query: str, k: int = 5,
    kinds: Optional[Sequence[str]] = None,
    tags: Optional[Sequence[str]] = None,
    min_score: float = 0.55,
) -> list[MemoryRecord]:
    """Semantic + filter retrieval. Cosine similarity threshold default 0.55."""
    _detect_backend_once()
    q_vec = _embed(query)
    if q_vec is None:
        return list_recent(company_id, limit=k, kinds=kinds, tags=tags)

    db = SessionLocal()
    try:
        from app.db.migrate_phase6 import Memory

        if _BACKEND == "pgvector":
            try:
                vec_str = json.dumps(q_vec.tolist())
                sql = """
                  SELECT id, 1 - (embedding_vec <=> (:vec)::vector) AS sim
                  FROM memories
                  WHERE company_id = :cid AND embedding_vec IS NOT NULL
                """
                params = {"vec": vec_str, "cid": company_id}
                if kinds:
                    sql += " AND kind = ANY(:kinds)"
                    params["kinds"] = list(kinds)
                sql += " ORDER BY embedding_vec <=> (:vec)::vector LIMIT :k"
                params["k"] = k * 4   # over-fetch, filter by tags + min_score in Python
                rows = db.execute(text(sql), params).fetchall()
                if not rows:
                    return []
                # Hydrate
                ids = [r.id for r in rows]
                sim_map = {r.id: float(r.sim) for r in rows}
                records = db.query(Memory).filter(Memory.id.in_(ids)).all()
                out = []
                for m in records:
                    sim = sim_map.get(m.id, 0.0)
                    if sim < min_score:
                        continue
                    if tags and not (set(tags) & set(m.tags or [])):
                        continue
                    out.append(_row_to_record(m, score=sim))
                # Sort by similarity desc, importance-weighted
                out.sort(key=lambda r: (r.score or 0) + 0.05 * r.importance, reverse=True)
                return out[:k]
            except Exception as e:
                log.warning("pgvector query failed, falling back to numpy: %s", e)

        # numpy fallback
        q = db.query(Memory).filter(Memory.company_id == company_id)
        if kinds:
            q = q.filter(Memory.kind.in_(list(kinds)))
        # Pull up to N candidates by recency — for company-scale this is fine.
        # Production scaling: cap, paginate, or rely on pgvector.
        candidates = q.order_by(desc(Memory.created_at)).limit(2000).all()

        scored = []
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return []
        for m in candidates:
            if not m.embedding_bytes:
                continue
            v = np.frombuffer(m.embedding_bytes, dtype=np.float32)
            if v.size == 0:
                continue
            vn = np.linalg.norm(v)
            if vn == 0:
                continue
            sim = float(np.dot(q_vec, v) / (q_norm * vn))
            if sim < min_score:
                continue
            if tags and not (set(tags) & set(m.tags or [])):
                continue
            scored.append((sim, m))

        scored.sort(key=lambda s: s[0] + 0.05 * float(s[1].importance or 0.5), reverse=True)
        results = [_row_to_record(m, score=s) for s, m in scored[:k]]

        # Update access tracking
        if results:
            now = datetime.utcnow()
            ids = [r.id for r in results]
            db.query(Memory).filter(Memory.id.in_(ids)).update(
                {"access_count": Memory.access_count + 1, "last_accessed_at": now},
                synchronize_session=False,
            )
            db.commit()
        return results
    finally:
        db.close()


# ===== List & maintenance =====
def list_recent(company_id: int, limit: int = 50,
                kinds: Optional[Sequence[str]] = None,
                tags: Optional[Sequence[str]] = None) -> list[MemoryRecord]:
    db = SessionLocal()
    try:
        from app.db.migrate_phase6 import Memory
        q = db.query(Memory).filter(Memory.company_id == company_id)
        if kinds:
            q = q.filter(Memory.kind.in_(list(kinds)))
        rows = q.order_by(desc(Memory.created_at)).limit(min(limit, 500)).all()
        if tags:
            rows = [r for r in rows if set(tags) & set(r.tags or [])]
        return [_row_to_record(r) for r in rows]
    finally:
        db.close()


def delete(company_id: int, memory_id: int) -> bool:
    db = SessionLocal()
    try:
        from app.db.migrate_phase6 import Memory
        m = db.query(Memory).filter(
            Memory.id == memory_id, Memory.company_id == company_id
        ).first()
        if not m:
            return False
        db.delete(m); db.commit()
        return True
    finally:
        db.close()


def update_importance(company_id: int, memory_id: int, importance: float) -> bool:
    db = SessionLocal()
    try:
        from app.db.migrate_phase6 import Memory
        m = db.query(Memory).filter(
            Memory.id == memory_id, Memory.company_id == company_id
        ).first()
        if not m:
            return False
        m.importance = max(0.0, min(1.0, importance))
        db.commit()
        return True
    finally:
        db.close()


def stats(company_id: int) -> dict:
    """Quick stats card for the UI."""
    db = SessionLocal()
    try:
        from app.db.migrate_phase6 import Memory
        from sqlalchemy import func
        rows = db.query(Memory.kind, func.count(Memory.id)).filter(
            Memory.company_id == company_id
        ).group_by(Memory.kind).all()
        total = db.query(func.count(Memory.id)).filter(
            Memory.company_id == company_id
        ).scalar() or 0
        return {
            "backend": get_backend_mode(),
            "total": int(total),
            "by_kind": {k: int(n) for k, n in rows},
        }
    finally:
        db.close()
