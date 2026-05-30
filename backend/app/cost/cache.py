"""Semantic cache.

Stores: prompt embedding + response in Redis. On lookup, finds nearest neighbor
by cosine similarity. If similarity >= threshold, returns cached response.

Why semantic, not exact: 'Draft an email for lead 5' and 'Write a cold email
for lead 5' should both hit the same cache entry. Their embeddings are very
close in vector space.

Tradeoffs vs an in-memory FAISS: Redis is simpler, no extra service, fine for
a few thousand entries per company. If this grows to millions, swap in a
proper vector DB. Cache key namespace is per-company so isolation is preserved.
"""
from __future__ import annotations
import json
import time
import hashlib
import logging
from dataclasses import dataclass

import httpx
import numpy as np
import redis

from app.config import settings

log = logging.getLogger(__name__)


@dataclass
class CacheHit:
    response: str
    model_used: str
    similarity: float
    cached_at: float


_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=False)
    return _redis_client


def _ns_key(company_id: int, suffix: str) -> str:
    return f"sa:cache:c{company_id}:{suffix}"


def _index_key(company_id: int) -> str:
    """Sorted set holding cache entry ids for this company."""
    return _ns_key(company_id, "idx")


def _entry_key(company_id: int, entry_id: str) -> str:
    return _ns_key(company_id, f"e:{entry_id}")


def embed(text: str) -> np.ndarray | None:
    """Call Ollama embedding endpoint. Returns L2-normalized vector or None on failure."""
    url = f"{settings.ollama_base_url}/api/embeddings"
    try:
        r = httpx.post(url, json={
            "model": settings.ollama_embed_model,
            "prompt": text[:8000],   # cap input
        }, timeout=15.0)
        r.raise_for_status()
        data = r.json()
        vec = np.array(data.get("embedding", []), dtype=np.float32)
        if vec.size == 0:
            return None
        n = np.linalg.norm(vec)
        if n == 0:
            return None
        return vec / n
    except Exception as e:
        log.warning("embedding failed: %s", e)
        return None


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    # Both vectors are L2-normalized → dot product is cosine
    return float(np.dot(a, b))


def _make_entry_id(prompt_key: str) -> str:
    return hashlib.sha256(prompt_key.encode()).hexdigest()[:16]


def lookup(company_id: int, system_prompt: str, user_prompt: str, tier: str,
           threshold: float | None = None) -> CacheHit | None:
    """Return a cache hit if any stored entry has similarity >= threshold."""
    threshold = threshold if threshold is not None else settings.cache_similarity_threshold

    prompt_key = f"[{tier}]\n{system_prompt}\n\n{user_prompt}"
    query_vec = embed(prompt_key)
    if query_vec is None:
        return None

    try:
        r = get_redis()
        entry_ids = r.zrange(_index_key(company_id), 0, -1)
    except Exception as e:
        log.warning("redis index read failed: %s", e)
        return None

    if not entry_ids:
        return None

    # Pull all entries (fine for <few thousand). Could batch with pipeline if needed.
    best: tuple[float, dict] | None = None
    try:
        pipe = r.pipeline()
        for eid in entry_ids:
            pipe.get(_entry_key(company_id, eid.decode() if isinstance(eid, bytes) else eid))
        results = pipe.execute()
    except Exception as e:
        log.warning("redis batch read failed: %s", e)
        return None

    for raw in results:
        if not raw:
            continue
        try:
            entry = json.loads(raw)
            stored_vec = np.array(entry["embedding"], dtype=np.float32)
        except Exception:
            continue
        sim = cosine(query_vec, stored_vec)
        if best is None or sim > best[0]:
            best = (sim, entry)

    if best and best[0] >= threshold:
        return CacheHit(
            response=best[1]["response"],
            model_used=best[1]["model_used"],
            similarity=best[0],
            cached_at=best[1]["cached_at"],
        )
    return None


def store(company_id: int, system_prompt: str, user_prompt: str, tier: str,
          response: str, model_used: str):
    """Store a prompt+response pair under the company's cache namespace."""
    prompt_key = f"[{tier}]\n{system_prompt}\n\n{user_prompt}"
    vec = embed(prompt_key)
    if vec is None:
        return

    entry_id = _make_entry_id(prompt_key + str(time.time()))
    payload = {
        "embedding": vec.tolist(),
        "response": response,
        "model_used": model_used,
        "cached_at": time.time(),
    }
    try:
        r = get_redis()
        pipe = r.pipeline()
        pipe.set(_entry_key(company_id, entry_id),
                 json.dumps(payload), ex=settings.cache_ttl_seconds)
        pipe.zadd(_index_key(company_id), {entry_id: time.time()})
        # cap index size at 500 entries per company; drop oldest
        pipe.zremrangebyrank(_index_key(company_id), 0, -501)
        pipe.expire(_index_key(company_id), settings.cache_ttl_seconds)
        pipe.execute()
    except Exception as e:
        log.warning("redis write failed: %s", e)


def stats(company_id: int) -> dict:
    """Cache size + memory stats for a company."""
    try:
        r = get_redis()
        size = r.zcard(_index_key(company_id))
        return {"entries": size, "available": True}
    except Exception:
        return {"entries": 0, "available": False}


def clear(company_id: int) -> int:
    """Wipe a company's cache. Returns number of entries removed."""
    try:
        r = get_redis()
        entry_ids = r.zrange(_index_key(company_id), 0, -1)
        if not entry_ids:
            return 0
        pipe = r.pipeline()
        for eid in entry_ids:
            eid_s = eid.decode() if isinstance(eid, bytes) else eid
            pipe.delete(_entry_key(company_id, eid_s))
        pipe.delete(_index_key(company_id))
        pipe.execute()
        return len(entry_ids)
    except Exception as e:
        log.warning("redis clear failed: %s", e)
        return 0
