"""Model router — Phase 5.

Phase 4 had two providers: local Ollama + Anthropic direct.
Phase 5 adds: AWS Bedrock + configurable Ollama URL (for Tailscale-to-home).

Provider selection:
  - cheap/standard tiers ALWAYS go to Ollama (local or remote-via-Tailscale).
  - quality/premium tiers go to whatever cloud the company has selected.
    The choice lives on companies.cloud_provider ('anthropic' or 'bedrock').

Why per-company: different tenants may have different compliance preferences,
different existing accounts, or different rate limits.
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
Provider = Literal["anthropic", "bedrock"]


@dataclass
class RouterResult:
    content: str
    model_used: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    was_cache_hit: bool
    was_downgraded: bool
    trace_span_id: Optional[int]
    provider_used: str = "local"   # 'local' | 'anthropic' | 'bedrock'


def _company_provider(company_id: int) -> Provider:
    """Return the cloud provider configured for this company, or the default."""
    db = SessionLocal()
    try:
        # Lazy import to avoid circulars during migration
        from app.db.migrate_phase3 import Company
        from app.db import model_extensions_p5  # noqa: F401 ensure column attr exists
        c = db.query(Company).filter(Company.id == company_id).first()
        if c is None:
            return settings.default_cloud_provider  # type: ignore[return-value]
        prov = getattr(c, "cloud_provider", None) or settings.default_cloud_provider
        return prov if prov in ("anthropic", "bedrock") else "anthropic"  # type: ignore[return-value]
    finally:
        db.close()


def _pick_model(tier: Tier, can_use_cloud: bool, must_downgrade: bool,
                provider: Provider) -> tuple[str, bool, str]:
    """Returns (model_name, was_downgraded, provider_used)."""
    if tier == "cheap":
        return settings.ollama_cheap_model, False, "local"
    if tier == "standard":
        return settings.ollama_model, False, "local"

    wants_cloud = tier in ("quality", "premium")
    if wants_cloud and can_use_cloud and not must_downgrade:
        if provider == "bedrock":
            model = (settings.bedrock_haiku_model_id if tier == "quality"
                     else settings.bedrock_sonnet_model_id)
            return model, False, "bedrock"
        # default: anthropic direct
        model = (settings.anthropic_haiku_model if tier == "quality"
                 else settings.anthropic_sonnet_model)
        return model, False, "anthropic"

    # Falling back to local
    return settings.ollama_model, wants_cloud, "local"


def _approx_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


async def _call_ollama(model: str, system: str, user: str) -> tuple[str, int, int]:
    """Calls whatever URL is in ollama_base_url. Could be localhost or Tailscale."""
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
    async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    content = (data.get("message") or {}).get("content", "")
    in_tok = data.get("prompt_eval_count") or _approx_tokens(system + user)
    out_tok = data.get("eval_count") or _approx_tokens(content)
    return content, in_tok, out_tok


async def _call_anthropic(model: str, system: str, user: str) -> tuple[str, int, int]:
    if not settings.anthropic_api_key:
        raise RuntimeError("anthropic_api_key not configured")
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=model, max_tokens=1024, system=system,
        messages=[{"role": "user", "content": user}],
    )
    text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "".join(text_parts), resp.usage.input_tokens, resp.usage.output_tokens


async def _call_bedrock(model_id: str, system: str, user: str) -> tuple[str, int, int]:
    """Call Claude via Bedrock. Uses ambient AWS credentials (IAM role on EC2,
    or AWS_PROFILE locally). Boto3 imports are lazy so the dep is optional.

    Bedrock's anthropic models use the same message schema as Anthropic's API,
    via the anthropic_version envelope. We use the converse API for cleanliness.
    """
    import boto3
    # boto3 is sync; run in thread to avoid blocking the event loop
    def _invoke():
        client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
        resp = client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": 1024, "temperature": settings.ollama_temperature},
        )
        out = resp["output"]["message"]["content"][0]["text"]
        usage = resp.get("usage", {})
        return out, int(usage.get("inputTokens", 0)), int(usage.get("outputTokens", 0))
    return await asyncio.to_thread(_invoke)


async def call_llm(system: str, user: str, tier: Tier = "standard",
                   agent_name: Optional[str] = None,
                   force_local: bool = False) -> RouterResult:
    ctx = tracing.get_context()
    company_id = ctx.company_id if ctx else None

    # No company context => no budget/cache/tracing. Just local.
    if company_id is None:
        content, in_tok, out_tok = await _call_ollama(settings.ollama_model, system, user)
        return RouterResult(
            content=content, model_used=settings.ollama_model,
            input_tokens=in_tok, output_tokens=out_tok,
            cost_usd=0.0, latency_ms=0,
            was_cache_hit=False, was_downgraded=False,
            trace_span_id=None, provider_used="local",
        )

    db = SessionLocal()
    try:
        status = budget_mod.get_status(db, company_id)
        provider = _company_provider(company_id)
        can_cloud = status.can_use_cloud and not force_local
        model, downgraded, provider_used = _pick_model(
            tier, can_cloud, status.must_downgrade, provider)

        span_id = None
        if ctx:
            span_id = tracing.start_span(
                db, ctx, kind="llm",
                model=model, input_preview=user[:200],
            )

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
                provider_used="cache",
            )

        # Dispatch to the right provider
        try:
            if provider_used == "bedrock":
                content, in_tok, out_tok = await _call_bedrock(model, system, user)
            elif provider_used == "anthropic":
                content, in_tok, out_tok = await _call_anthropic(model, system, user)
            else:
                content, in_tok, out_tok = await _call_ollama(model, system, user)
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

        try:
            cache_mod.store(company_id, system, user, tier, content, model)
        except Exception as e:
            log.warning("cache store failed: %s", e)

        return RouterResult(
            content=content, model_used=model,
            input_tokens=in_tok, output_tokens=out_tok,
            cost_usd=cost, latency_ms=latency_ms,
            was_cache_hit=False, was_downgraded=downgraded,
            trace_span_id=span_id, provider_used=provider_used,
        )
    finally:
        db.close()


def call_llm_sync(system: str, user: str, tier: Tier = "standard",
                  agent_name: Optional[str] = None) -> RouterResult:
    return asyncio.run(call_llm(system, user, tier, agent_name))
