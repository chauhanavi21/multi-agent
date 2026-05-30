"""QA agent — Phase 4 routed."""
from __future__ import annotations
from typing import AsyncGenerator
from app.agents.base import Worker, WorkerSpec, WorkerEvent, route_llm, parse_json_lenient
from app.tools.dev_tools import make_review_artifact


SPEC = WorkerSpec(
    name="dev_qa",
    display_name="QA reviewer",
    description="Reads specs/code/workflows and produces structured review notes. Read-only.",
    actions=["review", "list_test_cases"],
    capabilities=(
        "review(target, content): produce a structured review with severity-tagged findings. "
        "list_test_cases(target): list test cases that should exist for a given target."
    ),
)

ACTION_TIER = "cheap"   # structured classification, phi3 is fine


class QAWorker:
    spec = SPEC

    async def run(self, action: str, input: dict, task_id: str) -> AsyncGenerator[WorkerEvent, None]:
        if action == "review":
            async for ev in self._review(input, task_id):
                yield ev
        elif action == "list_test_cases":
            async for ev in self._test_cases(input, task_id):
                yield ev
        else:
            yield WorkerEvent("error", self.spec.name, f"Unknown action: {action}", task_id)

    async def _review(self, input: dict, task_id: str):
        target = input.get("target", "(unspecified)")
        content = input.get("content") or input.get("spec") or ""
        if not content:
            yield WorkerEvent("error", self.spec.name, "Missing 'content' or 'spec'", task_id)
            return

        yield WorkerEvent("thinking", self.spec.name, f"Reviewing: {target}", task_id)
        system = (
            "You are a strict QA reviewer. Read the target and return findings as JSON. "
            "Format: {\"severity\": \"info|warning|critical\", \"findings\": [\"...\", \"...\"]}. "
            "If no issues, severity=info and findings=[\"Looks good\"]. Output only raw JSON."
        )
        result = await route_llm(system, f"Target: {target}\n\n{content}",
                                  tier=ACTION_TIER, agent_name=self.spec.name)
        try:
            parsed = parse_json_lenient(result.content)
            artifact = make_review_artifact(
                target=target,
                findings=parsed.get("findings", []),
                severity=parsed.get("severity", "info"),
            )
        except Exception:
            artifact = make_review_artifact(target=target,
                                             findings=[result.content.strip()],
                                             severity="info")
        artifact["_router"] = {"model": result.model_used, "cost_usd": result.cost_usd,
                                "latency_ms": result.latency_ms,
                                "cache_hit": result.was_cache_hit}
        yield WorkerEvent("done", self.spec.name, artifact, task_id)

    async def _test_cases(self, input: dict, task_id: str):
        target = input.get("target", "(unspecified)")
        content = input.get("content") or input.get("spec") or target
        yield WorkerEvent("thinking", self.spec.name, f"Listing test cases for: {target}", task_id)
        system = (
            "List test cases as a JSON array of strings. Cover happy path, edge cases, "
            "and failure modes. Output only the JSON array, no fences."
        )
        result = await route_llm(system, str(content), tier=ACTION_TIER,
                                  agent_name=self.spec.name)
        try:
            cases = parse_json_lenient(result.content)
        except Exception:
            cases = [result.content.strip()]
        yield WorkerEvent("done", self.spec.name,
                          {"target": target, "test_cases": cases,
                           "_router": {"model": result.model_used,
                                       "cost_usd": result.cost_usd,
                                       "latency_ms": result.latency_ms,
                                       "cache_hit": result.was_cache_hit}},
                          task_id)
