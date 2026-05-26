"""QA agent — read-only review and analysis.

This agent cannot modify code or DB. It produces structured review notes.
"""
from __future__ import annotations
import asyncio
from typing import AsyncGenerator
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import Worker, WorkerSpec, WorkerEvent, get_llm, parse_json_lenient
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
            "Severity = max severity across findings. Be specific and actionable. "
            "If no issues, severity=info and findings=[\"Looks good\"]. "
            "Output only raw JSON, no markdown fences."
        )
        llm = get_llm(temperature=0.2)
        resp = await asyncio.to_thread(
            llm.invoke,
            [SystemMessage(content=system), HumanMessage(content=f"Target: {target}\n\n{content}")],
        )
        try:
            parsed = parse_json_lenient(resp.content)
            artifact = make_review_artifact(
                target=target,
                findings=parsed.get("findings", []),
                severity=parsed.get("severity", "info"),
            )
        except Exception:
            artifact = make_review_artifact(
                target=target,
                findings=[resp.content.strip()],
                severity="info",
            )
        yield WorkerEvent("done", self.spec.name, artifact, task_id)

    async def _test_cases(self, input: dict, task_id: str):
        target = input.get("target", "(unspecified)")
        content = input.get("content") or input.get("spec") or target

        yield WorkerEvent("thinking", self.spec.name, f"Listing test cases for: {target}", task_id)

        system = (
            "List test cases as a JSON array of strings. Cover happy path, edge cases, "
            "and failure modes. Be concrete. Output only the JSON array, no fences."
        )
        llm = get_llm(temperature=0.2)
        resp = await asyncio.to_thread(
            llm.invoke,
            [SystemMessage(content=system), HumanMessage(content=str(content))],
        )
        try:
            cases = parse_json_lenient(resp.content)
        except Exception:
            cases = [resp.content.strip()]
        yield WorkerEvent("done", self.spec.name,
                          {"target": target, "test_cases": cases}, task_id)
