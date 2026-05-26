"""Backend developer agent — produces API/DB specs, schema designs, server-side logic plans."""
from __future__ import annotations
import asyncio
from typing import AsyncGenerator
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import Worker, WorkerSpec, WorkerEvent, get_llm
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


class BackendDevWorker:
    spec = SPEC

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        prompt_map = {
            "design_endpoint": (
                "You are a senior backend engineer. Produce a FastAPI endpoint spec. "
                "Include: route, method, Pydantic request model, Pydantic response model, "
                "DB tables touched, edge cases, and a brief implementation sketch. "
                "Markdown formatted."
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
            yield WorkerEvent("error", self.spec.name, "Missing 'spec' or 'description' in input", task_id)
            return

        yield WorkerEvent("thinking", self.spec.name, f"Working on: {action}", task_id)

        llm = get_llm(temperature=0.3)
        resp = await asyncio.to_thread(
            llm.invoke,
            [SystemMessage(content=prompt_map[action]), HumanMessage(content=spec_text)],
        )
        artifact = make_spec_artifact(title=action, body=resp.content.strip())
        yield WorkerEvent("done", self.spec.name, artifact, task_id)
