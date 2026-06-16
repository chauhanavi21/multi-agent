"""Social analyst — Phase 6.

Adds two actions on top of Phase 4:
  - competitor_reels(handles, platform?): scrape (apify) or read (mock) top reels
  - script_reels(count?): write reel scripts inspired by competitor reels + memories
"""
from __future__ import annotations
import json
from typing import AsyncGenerator

from app.agents.base import Worker, WorkerSpec, WorkerEvent, route_llm, parse_json_lenient
from app.tools import social_tools, competitor_reels
from app.memory import store as memory


SPEC = WorkerSpec(
    name="social_analyst",
    display_name="Social analyst (CMO)",
    description="Analyzes platform trends + competitor content; writes new reel scripts.",
    actions=["trend_report", "hashtag_research", "sentiment_check",
             "competitor_reels", "script_reels"],
    capabilities=(
        "trend_report(topic, platform): full trend report. "
        "hashtag_research(topic, platform): hashtags only. "
        "sentiment_check(topic, platform): audience sentiment. "
        "competitor_reels(handles, platform?): pull top reels for competitor list. "
        "script_reels(count?): write fresh reel scripts using shared memory."
    ),
)

ACTION_TIER = "standard"
PLATFORMS = ("instagram", "facebook")


class SocialAnalystWorker:
    spec = SPEC

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        if action == "trend_report":
            async for ev in self._trend_report(input, task_id):
                yield ev
        elif action == "hashtag_research":
            async for ev in self._hashtag_research(input, task_id):
                yield ev
        elif action == "sentiment_check":
            async for ev in self._sentiment_check(input, task_id):
                yield ev
        elif action == "competitor_reels":
            async for ev in self._competitor_reels(input, task_id):
                yield ev
        elif action == "script_reels":
            async for ev in self._script_reels(input, task_id):
                yield ev
        else:
            yield WorkerEvent("error", self.spec.name, f"Unknown action: {action}", task_id)

    def _normalize_platforms(self, raw):
        if not raw or raw == "all":
            return list(PLATFORMS)
        if isinstance(raw, str):
            return [raw]
        return [p for p in raw if p in PLATFORMS]

    async def _trend_report(self, input, task_id):
        topic = input.get("topic", "")
        if not topic:
            yield WorkerEvent("error", self.spec.name, "Missing 'topic'", task_id); return
        platforms = self._normalize_platforms(input.get("platform"))
        yield WorkerEvent("tool", self.spec.name,
                          f"Pulling data: {topic} on {', '.join(platforms)}", task_id)
        data = {p: {
            "hashtags": social_tools.get_trending_hashtags(topic, p),
            "top_posts": social_tools.get_top_posts(topic, p, limit=3),
            "sentiment": social_tools.get_audience_sentiment(topic, p),
        } for p in platforms}
        system = (
            "You are a social media analyst. Summarize trend data in 3-4 sentences. "
            "Cite specific hashtags, content angles, sentiment."
        )
        r = await route_llm(system, f"Topic: {topic}\nData: {data}",
                             tier=ACTION_TIER, agent_name=self.spec.name)
        yield WorkerEvent("done", self.spec.name,
                          {"topic": topic, "platforms": platforms,
                           "summary": r.content.strip(), "data": data}, task_id)

    async def _hashtag_research(self, input, task_id):
        topic = input.get("topic", "")
        platforms = self._normalize_platforms(input.get("platform"))
        if not topic:
            yield WorkerEvent("error", self.spec.name, "Missing 'topic'", task_id); return
        result = {p: social_tools.get_trending_hashtags(topic, p) for p in platforms}
        yield WorkerEvent("done", self.spec.name,
                          {"topic": topic, "hashtags_by_platform": result}, task_id)

    async def _sentiment_check(self, input, task_id):
        topic = input.get("topic", "")
        platforms = self._normalize_platforms(input.get("platform"))
        if not topic:
            yield WorkerEvent("error", self.spec.name, "Missing 'topic'", task_id); return
        result = {p: social_tools.get_audience_sentiment(topic, p) for p in platforms}
        yield WorkerEvent("done", self.spec.name,
                          {"topic": topic, "sentiment_by_platform": result}, task_id)

    async def _competitor_reels(self, input, task_id):
        company_id = int(input["company_id"])
        handles = input.get("handles") or input.get("competitors") or []
        if isinstance(handles, str):
            handles = [h.strip() for h in handles.split(",") if h.strip()]
        platform = input.get("platform", "instagram")
        if not handles:
            yield WorkerEvent("error", self.spec.name, "Missing 'handles'", task_id); return

        yield WorkerEvent("tool", self.spec.name,
                          f"Pulling reels for: {', '.join(handles)}", task_id)
        res = competitor_reels.scrape_competitor_reels(
            company_id=company_id, handles=handles, platform=platform)

        # Memorize the top reels
        for reel in res.get("sample", [])[:3]:
            content = (
                f"{reel['handle']} on {reel['platform']}: "
                f"{(reel.get('caption') or '')[:200]} | "
                f"views={reel.get('views')}, likes={reel.get('likes')}"
            )
            memory.remember(
                company_id=company_id, kind="competitor", content=content[:600],
                tags=["competitor", "reel", platform, reel["handle"]],
                source_agent=self.spec.name, importance=0.6,
            )

        yield WorkerEvent("done", self.spec.name, res, task_id)

    async def _script_reels(self, input, task_id):
        from app.db.migrate_phase6 import ReelScript
        from app.db.models import SessionLocal

        company_id = int(input["company_id"])
        count = max(1, min(int(input.get("count", 3)), 5))

        # Pull recent top reels for inspiration
        top = competitor_reels.get_top_reels(company_id, limit=5)
        # Plus memory: brand voice + winning patterns
        mems = memory.retrieve(
            company_id, "brand voice and what content is winning on social",
            k=5, kinds=("pattern", "preference", "competitor", "win"),
        )
        memory_block = "\n".join(f"- [{m.kind}] {m.content}" for m in mems) or "(none)"
        inspiration = "\n".join(
            f"- @{r['handle']}: {(r.get('caption') or '')[:160]} (views={r.get('views')})"
            for r in top
        ) or "(no competitor data — set up reels first)"

        yield WorkerEvent("tool", self.spec.name,
                          f"Generating {count} scripts; {len(top)} top reels + {len(mems)} memories",
                          task_id)

        system = (
            "You are a short-form video scriptwriter for a B2B brand. Write reel scripts "
            "that are punchy, specific, and grounded in what the brand has been learning. "
            "Each script has a HOOK (one line, first 3 seconds), BODY (15-30 seconds of "
            "spoken content), and CTA (one line). "
            f"Output strictly JSON: {{\"scripts\":[{{\"title\":\"\",\"hook\":\"\",\"body\":\"\",\"cta\":\"\"}}]}} "
            f"with exactly {count} items."
        )
        user_prompt = (
            f"What's working in our memory:\n{memory_block}\n\n"
            f"Top competitor reels to learn from (not copy):\n{inspiration}\n\n"
            f"Write {count} fresh scripts."
        )
        r = await route_llm(system, user_prompt, tier="quality", agent_name=self.spec.name)

        try:
            parsed = parse_json_lenient(r.content)
            scripts = parsed.get("scripts", [])[:count]
        except Exception:
            scripts = []

        # Persist
        saved_ids = []
        db = SessionLocal()
        try:
            for s in scripts:
                row = ReelScript(
                    company_id=company_id,
                    title=(s.get("title") or "Untitled")[:200],
                    hook=(s.get("hook") or "")[:500],
                    body=(s.get("body") or "")[:2000],
                    cta=(s.get("cta") or "")[:500],
                    inspired_by_reel_ids=[t["id"] for t in top],
                )
                db.add(row); db.commit(); db.refresh(row)
                saved_ids.append(row.id)
        finally:
            db.close()

        yield WorkerEvent("done", self.spec.name,
                          {"count": len(saved_ids), "script_ids": saved_ids,
                           "scripts": scripts,
                           "_router": {"model": r.model_used, "cost_usd": r.cost_usd,
                                       "cache_hit": r.was_cache_hit}},
                          task_id)
