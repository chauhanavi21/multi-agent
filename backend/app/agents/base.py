"""Worker contract + the new router-aware LLM helper.

Phase 4: agents call `route_llm(...)` instead of constructing a raw ChatOllama.
The old `get_llm()` is kept for backward compat (returns a ChatOllama wired to
the local default model — used only by paths we haven't migrated yet).
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Protocol, Literal

from langchain_ollama import ChatOllama
from app.config import settings
from app.cost.router import call_llm, RouterResult


@dataclass
class WorkerEvent:
    type: str
    agent: str
    content: Any
    task_id: str | None = None

    def to_dict(self):
        return {"type": self.type, "agent": self.agent,
                "content": self.content, "task_id": self.task_id}


@dataclass
class WorkerSpec:
    name: str
    display_name: str
    description: str
    actions: list[str]
    capabilities: str = ""


class Worker(Protocol):
    spec: WorkerSpec
    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        ...


def get_llm(temperature: float | None = None, model: str | None = None):
    """Backward-compatible local LLM. New code should use route_llm()."""
    return ChatOllama(
        model=model or settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=temperature if temperature is not None else settings.ollama_temperature,
    )


Tier = Literal["cheap", "standard", "quality", "premium"]


async def route_llm(system: str, user: str, tier: Tier = "standard",
                    agent_name: str | None = None) -> RouterResult:
    """The Phase 4 way to call any model. Picks model per tier+budget+cache."""
    return await call_llm(system, user, tier=tier, agent_name=agent_name)


def parse_json_lenient(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    starts = [i for i in (raw.find("{"), raw.find("[")) if i >= 0]
    ends = [i for i in (raw.rfind("}"), raw.rfind("]")) if i >= 0]
    if starts and ends:
        raw = raw[min(starts): max(ends) + 1]
    return json.loads(raw)
