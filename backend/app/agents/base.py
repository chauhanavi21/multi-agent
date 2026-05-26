"""Shared contract every worker agent implements.

A worker is a callable: input dict -> async generator of events -> final result.
This lets the manager treat every specialist identically.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Protocol
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from app.config import settings


@dataclass
class WorkerEvent:
    """Streamed back to the UI as the worker runs."""
    type: str                  # plan, tool, thinking, partial, done, error
    agent: str
    content: Any
    task_id: str | None = None

    def to_dict(self):
        return {
            "type": self.type,
            "agent": self.agent,
            "content": self.content,
            "task_id": self.task_id,
        }


@dataclass
class WorkerSpec:
    name: str                      # "sales", "dev_backend", etc.
    display_name: str              # "Sales agent"
    description: str               # what this agent does
    actions: list[str]             # action names the manager can invoke
    capabilities: str = ""         # short string the manager sees during planning


class Worker(Protocol):
    spec: WorkerSpec

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        ...


def get_llm(temperature: float | None = None, model: str | None = None):
    return ChatOllama(
        model=model or settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=temperature if temperature is not None else settings.ollama_temperature,
    )


def parse_json_lenient(raw: str) -> Any:
    """LLMs often wrap JSON in ``` or add prose. Extract best-effort."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    # find first { or [ and last } or ]
    starts = [i for i in (raw.find("{"), raw.find("[")) if i >= 0]
    ends = [i for i in (raw.rfind("}"), raw.rfind("]")) if i >= 0]
    if starts and ends:
        raw = raw[min(starts): max(ends) + 1]
    return json.loads(raw)
