"""Backend developer agent — Phase 4 routed."""
from __future__ import annotations
from typing import AsyncGenerator
from app.agents.base import Worker, WorkerSpec, WorkerEvent, route_llm
from app.tools.dev_tools import make_spec_artifact


SPEC = WorkerSpec(
    name="dev_backend",
    display_name="Backend developer",
    description="Designs APIs, database schemas, server-side logic. Python/FastAPI/SQL focus.",
    actions=["design_endpoint", "design_schema", "write_function"],
    capabilities=(
        "design_endpoint(spec): produce a FastAPI route spec with request/response models. "
        "design_schema(spec): produce a SQL schema with migrations. "
        "write_function(spec): write a Python function with type hints and docstring."
    ),
)


# Quality tier — dev specs are user-visible and worth nicer prose if cloud is on
ACTION_TIER = "standard"   # bump to "quality" if you want polished output


class BackendDevWorker:
    spec = SPEC

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        prompt_map = {
            "design_endpoint": (
                "You are a senior backend engineer. Produce a FastAPI endpoint spec. "
                "Include: route, method, Pydantic request model, Pydantic response model, "
                "DB tables touched, edge cases, and a brief implementation sketch. Markdown."
            ),
            "design_schema": (
                "You are a senior backend engineer. Produce a Postgres schema. "
                "Include: tables with columns + types + constraints, indexes, foreign keys, "
                "and SQLAlchemy model snippets. Markdown."
            ),
            "write_function": (
                "You are a senior backend engineer. Write a Python function. "
                "Include: full signature with type hints, docstring, implementation, "
                "and a usage example. Return as a single markdown code block."
            ),
        }
        if action not in prompt_map:
            yield WorkerEvent("error", self.spec.name, f"Unknown action: {action}", task_id)
            return

        spec_text = input.get("spec") or input.get("description") or ""
        if not spec_text:
            yield WorkerEvent("error", self.spec.name, "Missing 'spec' or 'description'", task_id)
            return

        yield WorkerEvent("thinking", self.spec.name, f"Working on: {action}", task_id)

        result = await route_llm(prompt_map[action], spec_text, tier=ACTION_TIER,
                                  agent_name=self.spec.name)
        artifact = make_spec_artifact(title=action, body=result.content.strip())
        artifact["_router"] = {
            "model": result.model_used, "cost_usd": result.cost_usd,
            "latency_ms": result.latency_ms, "cache_hit": result.was_cache_hit,
        }
        yield WorkerEvent("done", self.spec.name, artifact, task_id)
