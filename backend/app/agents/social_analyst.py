"""Social analyst — analyzes trends on Facebook + Instagram (mocked APIs)."""
from __future__ import annotations
import asyncio
from typing import AsyncGenerator
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import Worker, WorkerSpec, WorkerEvent, get_llm
from app.tools import social_tools


SPEC = WorkerSpec(
    name="social_analyst",
    display_name="Social analyst",
    description="Analyzes Facebook + Instagram trends, hashtags, top posts, sentiment.",
    actions=["trend_report", "hashtag_research", "sentiment_check"],
    capabilities=(
        "trend_report(topic, platform): full trend report (hashtags + posts + sentiment + summary). "
        "hashtag_research(topic, platform): trending hashtags only. "
        "sentiment_check(topic, platform): audience sentiment for a topic."
    ),
)


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
        else:
            yield WorkerEvent("error", self.spec.name, f"Unknown action: {action}", task_id)

    def _normalize_platforms(self, raw):
        if not raw or raw == "all":
            return list(PLATFORMS)
        if isinstance(raw, str):
            return [raw]
        return [p for p in raw if p in PLATFORMS]

    async def _trend_report(self, input: dict, task_id: str):
        topic = input.get("topic", "")
        if not topic:
            yield WorkerEvent("error", self.spec.name, "Missing 'topic'", task_id)
            return

        platforms = self._normalize_platforms(input.get("platform"))
        yield WorkerEvent("tool", self.spec.name,
                          f"Pulling data: {topic} on {', '.join(platforms)}", task_id)

        data = {}
        for p in platforms:
            data[p] = {
                "hashtags": social_tools.get_trending_hashtags(topic, p),
                "top_posts": social_tools.get_top_posts(topic, p, limit=3),
                "sentiment": social_tools.get_audience_sentiment(topic, p),
            }

        yield WorkerEvent("thinking", self.spec.name,
                          "Synthesizing 1-paragraph executive summary...", task_id)
        system = (
            "You are a social media analyst. Given raw trend data, write a 3-4 sentence "
            "executive summary highlighting: the strongest hashtag opportunity, one notable "
            "content angle, and the dominant sentiment. Be specific, no fluff."
        )
        llm = get_llm(temperature=0.3)
        resp = await asyncio.to_thread(
            llm.invoke,
            [SystemMessage(content=system),
             HumanMessage(content=f"Topic: {topic}\nData: {data}")],
        )
        yield WorkerEvent("done", self.spec.name,
                          {"topic": topic, "platforms": platforms,
                           "summary": resp.content.strip(), "data": data},
                          task_id)

    async def _hashtag_research(self, input: dict, task_id: str):
        topic = input.get("topic", "")
        platforms = self._normalize_platforms(input.get("platform"))
        if not topic:
            yield WorkerEvent("error", self.spec.name, "Missing 'topic'", task_id)
            return
        yield WorkerEvent("tool", self.spec.name, f"Hashtag research for: {topic}", task_id)
        result = {p: social_tools.get_trending_hashtags(topic, p) for p in platforms}
        yield WorkerEvent("done", self.spec.name,
                          {"topic": topic, "hashtags_by_platform": result}, task_id)

    async def _sentiment_check(self, input: dict, task_id: str):
        topic = input.get("topic", "")
        platforms = self._normalize_platforms(input.get("platform"))
        if not topic:
            yield WorkerEvent("error", self.spec.name, "Missing 'topic'", task_id)
            return
        yield WorkerEvent("tool", self.spec.name, f"Sentiment check: {topic}", task_id)
        result = {p: social_tools.get_audience_sentiment(topic, p) for p in platforms}
        yield WorkerEvent("done", self.spec.name,
                          {"topic": topic, "sentiment_by_platform": result}, task_id)
