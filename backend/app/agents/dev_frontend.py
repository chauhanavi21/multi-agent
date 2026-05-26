"""Frontend developer agent — React component specs, CSS, UX flows."""
from __future__ import annotations
import asyncio
from typing import AsyncGenerator
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import Worker, WorkerSpec, WorkerEvent, get_llm
from app.tools.dev_tools import make_spec_artifact


SPEC = WorkerSpec(
    name="dev_frontend",
    display_name="Frontend developer",
    description="Designs React components, UI flows, CSS, accessibility patterns.",
    actions=["design_component", "design_flow", "write_component"],
    capabilities=(
        "design_component(spec): produce a React component spec with props + states. "
        "design_flow(spec): describe a multi-screen user flow with states + transitions. "
        "write_component(spec): write a full React functional component."
    ),
)


class FrontendDevWorker:
    spec = SPEC

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        prompt_map = {
            "design_component": (
                "You are a senior frontend engineer. Produce a React component spec. "
                "Include: component name, props (with types), states, handlers, accessibility "
                "considerations, and a brief render-tree sketch. Markdown."
            ),
            "design_flow": (
                "You are a senior frontend engineer. Describe a user flow across screens. "
                "Include: screens listed in order, what changes at each, decision points, "
                "loading/error states. Markdown."
            ),
            "write_component": (
                "You are a senior frontend engineer. Write a full React functional component "
                "using hooks. Include: the component code in a single markdown code block, "
                "followed by a short usage example."
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

        llm = get_llm(temperature=0.4)
        resp = await asyncio.to_thread(
            llm.invoke,
            [SystemMessage(content=prompt_map[action]), HumanMessage(content=spec_text)],
        )
        artifact = make_spec_artifact(title=action, body=resp.content.strip())
        yield WorkerEvent("done", self.spec.name, artifact, task_id)
