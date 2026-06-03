"""Frontend developer agent — Phase 4 routed."""
from __future__ import annotations
from typing import AsyncGenerator
from app.agents.base import Worker, WorkerSpec, WorkerEvent, route_llm
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

ACTION_TIER = "standard"


class FrontendDevWorker:
    spec = SPEC

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        prompt_map = {
            "design_component": (
                "You are a senior frontend engineer. Produce a React component spec. "
                "Include: component name, props (with types), states, handlers, accessibility, "
                "and a render-tree sketch. Markdown."
            ),
            "design_flow": (
                "You are a senior frontend engineer. Describe a user flow across screens. "
                "Include screens in order, what changes at each, decisions, loading/error states."
            ),
            "write_component": (
                "You are a senior frontend engineer. Write a full React functional component "
                "with hooks. Include code in one markdown block plus a short usage example."
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
