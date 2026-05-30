"""Model router.

Public API:
    call_llm(system, user, tier, agent_name=None, force_local=False) -> RouterResult

The router:
  1. Picks a tier-appropriate model considering company budget + cloud flag.
  2. Checks semantic cache; returns hit if similar enough.
  3. Calls the chosen model (Ollama for local, Anthropic SDK for cloud).
  4. Writes a usage_record and a trace span.
  5. Stores the response in the cache.

Tier definitions:
  cheap     -> phi3:mini (local)
  standard  -> llama3.1:8b (local)
  quality   -> Claude Haiku (cloud) | llama3.1:8b (fallback)
  premium   -> Claude Sonnet (cloud) | llama3.1:8b (fallback)
"""
from __future__ import annotations
import time
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Literal

import httpx

from app.config import settings
from app.cost import cache as cache_mod
from app.cost import pricing
from app.cost import budget as budget_mod
from app.cost import tracing
from app.db.models import SessionLocal

log = logging.getLogger(__name__)


Tier = Literal["cheap", "standard", "quality", "premium"]


@dataclass
class RouterResult:
    content: str
    model_used: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    was_cache_hit: bool
    was_downgraded: bool       # tier wanted cloud but got local
    trace_span_id: Optional[int]


def _pick_model(tier: Tier, can_use_cloud: bool, must_downgrade: bool) -> tuple[str, bool]:
    """Returns (model_name, was_downgraded)."""
    if tier == "cheap":
        return settings.ollama_cheap_model, False
    if tier == "standard":
        return settings.ollama_model, False

    # quality / premium want cloud
    wants_cloud = tier in ("quality", "premium")
    if wants_cloud and can_use_cloud and not must_downgrade:
        return (
            settings.anthropic_haiku_model if tier == "quality"
            else settings.anthropic_sonnet_model,
            False,
        )
    # falling back to local
    return settings.ollama_model, wants_cloud


def _approx_tokens(text: str) -> int:
    """Rough token estimate when the provider doesn't give us a count.
    ~4 chars/token for English. Good enough for budget math, not for billing."""
    if not text:
        return 0
    return max(1, len(text) // 4)


async def _call_ollama(model: str, system: str, user: str) -> tuple[str, int, int]:
    """Returns (content, input_tokens, output_tokens). Tokens are approx."""
    url = f"{settings.ollama_base_url}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": settings.ollama_temperature},
    }
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    content = (data.get("message") or {}).get("content", "")
    # Ollama returns prompt_eval_count + eval_count when available
    in_tok = data.get("prompt_eval_count") or _approx_tokens(system + user)
    out_tok = data.get("eval_count") or _approx_tokens(content)
    return content, in_tok, out_tok


async def _call_anthropic(model: str, system: str, user: str) -> tuple[str, int, int]:
    """Real Claude API call. Raises if no key set."""
    if not settings.anthropic_api_key:
        raise RuntimeError("anthropic_api_key not configured")
    # Lazy import so the dep is only required when actually used
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    # response content is a list of blocks
    text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    content = "".join(text_parts)
    in_tok = resp.usage.input_tokens
    out_tok = resp.usage.output_tokens
    return content, in_tok, out_tok


async def call_llm(system: str, user: str, tier: Tier = "standard",
                   agent_name: Optional[str] = None,
                   force_local: bool = False) -> RouterResult:
    """Main entry point. Honors trace context if set."""
    ctx = tracing.get_context()
    company_id = ctx.company_id if ctx else None

    # No company context => no budgets, no cache, no tracing. Just local.
    if company_id is None:
        content, in_tok, out_tok = await _call_ollama(settings.ollama_model, system, user)
        return RouterResult(
            content=content, model_used=settings.ollama_model,
            input_tokens=in_tok, output_tokens=out_tok,
            cost_usd=0.0, latency_ms=0,
            was_cache_hit=False, was_downgraded=False, trace_span_id=None,
        )

    db = SessionLocal()
    try:
        status = budget_mod.get_status(db, company_id)
        can_cloud = status.can_use_cloud and not force_local
        model, downgraded = _pick_model(tier, can_cloud, status.must_downgrade)

        # Trace span open
        span_id = None
        if ctx:
            span_id = tracing.start_span(
                db, ctx, kind="llm",
                model=model, input_preview=user[:200],
            )

        # Cache lookup
        t0 = time.monotonic()
        hit = cache_mod.lookup(company_id, system, user, tier)
        if hit:
            latency_ms = int((time.monotonic() - t0) * 1000)
            if span_id:
                tracing.end_span(db, span_id, status="ok",
                                 output_preview=hit.response[:200],
                                 input_tokens=0, output_tokens=0,
                                 cost_usd=0.0, latency_ms=latency_ms,
                                 was_cache_hit=True)
                budget_mod.record_usage(db, company_id, model=hit.model_used,
                                         input_tokens=0, output_tokens=0, cost_usd=0.0,
                                         agent_name=agent_name, trace_span_id=span_id,
                                         was_cache_hit=True)
            return RouterResult(
                content=hit.response, model_used=hit.model_used,
                input_tokens=0, output_tokens=0,
                cost_usd=0.0, latency_ms=latency_ms,
                was_cache_hit=True, was_downgraded=False,
                trace_span_id=span_id,
            )

        # Real call
        try:
            if pricing.is_local(model):
                content, in_tok, out_tok = await _call_ollama(model, system, user)
            else:
                content, in_tok, out_tok = await _call_anthropic(model, system, user)
        except Exception as e:
            if span_id:
                tracing.end_span(db, span_id, status="error", error=str(e),
                                 latency_ms=int((time.monotonic() - t0) * 1000))
            raise

        latency_ms = int((time.monotonic() - t0) * 1000)
        cost = pricing.calc_cost(model, in_tok, out_tok)

        if span_id:
            tracing.end_span(db, span_id, status="ok",
                             output_preview=content[:200],
                             input_tokens=in_tok, output_tokens=out_tok,
                             cost_usd=cost, latency_ms=latency_ms,
                             was_cache_hit=False)
            budget_mod.record_usage(db, company_id, model=model,
                                     input_tokens=in_tok, output_tokens=out_tok,
                                     cost_usd=cost, agent_name=agent_name,
                                     trace_span_id=span_id, was_cache_hit=False)

        # Cache for next time (best effort)
        try:
            cache_mod.store(company_id, system, user, tier, content, model)
        except Exception as e:
            log.warning("cache store failed: %s", e)

        return RouterResult(
            content=content, model_used=model,
            input_tokens=in_tok, output_tokens=out_tok,
            cost_usd=cost, latency_ms=latency_ms,
            was_cache_hit=False, was_downgraded=downgraded,
            trace_span_id=span_id,
        )
    finally:
        db.close()


def call_llm_sync(system: str, user: str, tier: Tier = "standard",
                  agent_name: Optional[str] = None) -> RouterResult:
    """Sync wrapper for code paths that aren't async yet."""
    return asyncio.run(call_llm(system, user, tier, agent_name))
