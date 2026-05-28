"""Manager agent — Phase 3: company-scoped.

Same flow as Phase 2 (plan → execute DAG → aggregate), but every worker
gets `company_id` injected into its input. Chat sessions are also created
with the right company_id and user_id.
"""
from __future__ import annotations
import asyncio
import json
from typing import AsyncGenerator
from langchain_core.messages import HumanMessage, SystemMessage

from app.db.models import SessionLocal
from app.db.migrate_phase2 import ChatSession, AgentMessage
from app.agents.base import WorkerEvent, get_llm, parse_json_lenient
from app.agents import registry
from app.tools import task_queue


PLAN_SYSTEM_PROMPT = """You are a Manager agent coordinating a team of specialist AI agents.
Given a user's request, decompose it into a JSON plan of tasks.

Available agents and their actions:
{capabilities}

Rules:
- Output ONLY a JSON object: {{"tasks": [...], "reply_hint": "..."}}.
- Each task: {{"id": "t1", "agent": "<name>", "action": "<action>", "input": {{...}}, "depends_on": []}}.
- task ids are t1, t2, t3, ... unique within the plan.
- depends_on lists task ids that must complete before this one starts.
- If a task needs output from a dependency, write the input value as "${{tN.output.field}}".
- Keep plans SMALL: 1-5 tasks max.
- If the user request is conversational, output {{"tasks": [], "reply_hint": "<short reply>"}}.
- Do NOT include company_id in inputs — that's injected automatically.
- No markdown, no code fences. Raw JSON only.
"""


AGGREGATE_SYSTEM_PROMPT = """You are the Manager agent. Workers have completed their tasks.
Write a concise reply to the user that synthesizes their outputs.

Rules:
- Address the user directly.
- Reference specific artifacts (draft id, lead names, hashtags, etc.).
- Under 150 words unless detail was requested.
- If a task errored, mention it briefly and suggest next step.
- Plain text reply. No JSON.
"""


def _substitute_refs(value, outputs: dict):
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        ref = value[2:-1]
        parts = ref.split(".")
        if len(parts) < 2 or parts[1] != "output":
            return value
        task_key = parts[0]
        if task_key not in outputs:
            return value
        node = outputs[task_key]
        for p in parts[2:]:
            if isinstance(node, dict) and p in node:
                node = node[p]
            elif isinstance(node, list) and p.isdigit() and int(p) < len(node):
                node = node[int(p)]
            else:
                return value
        return node
    if isinstance(value, dict):
        return {k: _substitute_refs(v, outputs) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_refs(v, outputs) for v in value]
    return value


async def _run_one_task(task_spec: dict, db_task_id: int, outputs: dict,
                        event_queue: asyncio.Queue, company_id: int):
    agent_name = task_spec["agent"]
    action = task_spec["action"]
    task_key = task_spec["id"]
    raw_input = task_spec.get("input", {}) or {}
    resolved_input = _substitute_refs(raw_input, outputs)
    # Inject company_id into every worker call. This is what enforces isolation.
    resolved_input = {**resolved_input, "company_id": company_id}

    worker = registry.get_worker(agent_name)
    db = SessionLocal()
    try:
        task_queue.mark_running(db, db_task_id)
        await event_queue.put(WorkerEvent("status", agent_name,
                                          {"task_key": task_key, "status": "running"}, task_key))

        if worker is None:
            err = f"Unknown agent: {agent_name}"
            task_queue.mark_error(db, db_task_id, err)
            await event_queue.put(WorkerEvent("error", agent_name, err, task_key))
            outputs[task_key] = {"error": err}
            return

        final_output = None
        try:
            async for ev in worker.run(action, resolved_input, task_id=task_key):
                await event_queue.put(ev)
                if ev.type == "done":
                    final_output = ev.content
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            task_queue.mark_error(db, db_task_id, err)
            await event_queue.put(WorkerEvent("error", agent_name, err, task_key))
            outputs[task_key] = {"error": err}
            return

        outputs[task_key] = final_output or {}
        task_queue.mark_ok(db, db_task_id,
                           outputs[task_key] if isinstance(outputs[task_key], dict)
                           else {"value": outputs[task_key]})
        await event_queue.put(WorkerEvent("status", agent_name,
                                          {"task_key": task_key, "status": "ok"}, task_key))
    finally:
        db.close()


async def _execute_dag(tasks: list[dict], db_task_ids: dict, event_queue: asyncio.Queue,
                       company_id: int) -> dict:
    outputs: dict = {}
    remaining = {t["id"]: t for t in tasks}
    in_flight: dict[str, asyncio.Task] = {}

    while remaining or in_flight:
        for tid in list(remaining.keys()):
            t = remaining[tid]
            deps = t.get("depends_on") or []
            if all(d in outputs for d in deps):
                fut = asyncio.create_task(
                    _run_one_task(t, db_task_ids[tid], outputs, event_queue, company_id)
                )
                in_flight[tid] = fut
                del remaining[tid]

        if not in_flight:
            for tid, t in remaining.items():
                await event_queue.put(WorkerEvent(
                    "error", "manager",
                    f"Task {tid} skipped — unresolved deps: {t.get('depends_on')}", tid,
                ))
            break

        done, _ = await asyncio.wait(in_flight.values(), return_when=asyncio.FIRST_COMPLETED)
        for fut in done:
            for tid, f in list(in_flight.items()):
                if f is fut:
                    del in_flight[tid]
                    break

    return outputs


async def run_manager(session_id: int, user_message: str,
                      company_id: int, user_id: int) -> AsyncGenerator[dict, None]:
    """Run a full manager turn — company-scoped."""
    db = SessionLocal()
    try:
        db.add(AgentMessage(session_id=session_id, role="user", content=user_message))
        db.commit()
    finally:
        db.close()

    yield {"type": "manager_start", "agent": "manager", "content": "Planning..."}

    sys_prompt = PLAN_SYSTEM_PROMPT.format(capabilities=registry.capabilities_prompt())
    llm = get_llm(temperature=0.2)
    plan_resp = await asyncio.to_thread(
        llm.invoke,
        [SystemMessage(content=sys_prompt), HumanMessage(content=user_message)],
    )
    try:
        plan = parse_json_lenient(plan_resp.content)
    except Exception as e:
        yield {"type": "error", "agent": "manager",
               "content": f"Failed to parse plan: {e}\nRaw: {plan_resp.content[:300]}"}
        return

    tasks = plan.get("tasks", []) or []
    reply_hint = plan.get("reply_hint", "")
    yield {"type": "plan", "agent": "manager",
           "content": {"tasks": tasks, "reply_hint": reply_hint}}

    if not tasks:
        db = SessionLocal()
        try:
            db.add(AgentMessage(session_id=session_id, role="manager",
                                content=reply_hint or "Got it."))
            db.commit()
        finally:
            db.close()
        yield {"type": "manager_reply", "agent": "manager",
               "content": reply_hint or "Got it."}
        return

    db_task_ids: dict[str, int] = {}
    db = SessionLocal()
    try:
        for t in tasks:
            tid = task_queue.create_task(
                db, session_id=session_id, task_key=t["id"], agent_name=t["agent"],
                action=t["action"], input_json=t.get("input") or {},
                depends_on=t.get("depends_on") or [],
            )
            db_task_ids[t["id"]] = tid
    finally:
        db.close()

    event_queue: asyncio.Queue = asyncio.Queue()

    async def runner():
        try:
            outs = await _execute_dag(tasks, db_task_ids, event_queue, company_id)
            await event_queue.put({"__final__": outs})
        except Exception as e:
            await event_queue.put(WorkerEvent("error", "manager", str(e)))
            await event_queue.put({"__final__": {}})

    runner_task = asyncio.create_task(runner())

    final_outputs = None
    while True:
        item = await event_queue.get()
        if isinstance(item, dict) and "__final__" in item:
            final_outputs = item["__final__"]
            break
        if isinstance(item, WorkerEvent):
            yield item.to_dict()
        else:
            yield item

    await runner_task

    yield {"type": "aggregating", "agent": "manager", "content": "Synthesizing reply..."}
    summary_input = {
        "user_message": user_message,
        "reply_hint": reply_hint,
        "task_outputs": final_outputs or {},
    }
    agg_resp = await asyncio.to_thread(
        llm.invoke,
        [SystemMessage(content=AGGREGATE_SYSTEM_PROMPT),
         HumanMessage(content=json.dumps(summary_input, default=str)[:8000])],
    )
    reply = agg_resp.content.strip()

    db = SessionLocal()
    try:
        db.add(AgentMessage(session_id=session_id, role="manager", content=reply,
                            metadata_json={"task_count": len(tasks)}))
        db.commit()
    finally:
        db.close()

    yield {"type": "manager_reply", "agent": "manager", "content": reply}
