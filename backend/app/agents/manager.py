"""Manager agent — Phase 4.

New in Phase 4:
- Sets trace context at the top of the run so workers inherit company_id
  and parent_span_id for the cost router.
- Planning uses 'cheap' tier (phi3 is fine for JSON DAG output).
- Aggregation uses 'quality' tier so user-facing replies can use Haiku if
  cloud is enabled.
"""
from __future__ import annotations
import asyncio
import json
from typing import AsyncGenerator

from app.db.models import SessionLocal
from app.db.migrate_phase2 import ChatSession, AgentMessage
from app.agents.base import WorkerEvent, route_llm, parse_json_lenient
from app.agents import registry
from app.billing.plans import get_company_plan, resolve_manager_aggregate_tier
from app.tools import task_queue
from app.cost import tracing


PLAN_SYSTEM_PROMPT = """You are a Manager agent coordinating a team of specialist AI agents.
Given a user's request, decompose it into a JSON plan of tasks.

Available agents and their actions:
{capabilities}

Rules:
- Output ONLY a JSON object: {{"tasks": [...], "reply_hint": "..."}}.
- Each task: {{"id": "t1", "agent": "<name>", "action": "<action>", "input": {{...}}, "depends_on": []}}.
- task ids are t1, t2, t3, ... unique within the plan.
- depends_on lists task ids that must complete first.
- If a task needs output from a dependency, write the value as "${{tN.output.field}}".
- Keep plans SMALL: 1-5 tasks max.
- If conversational, output {{"tasks": [], "reply_hint": "<short reply>"}}.
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


async def _run_one_task(task_spec, db_task_id, outputs, event_queue,
                        company_id, session_id):
    agent_name = task_spec["agent"]
    action = task_spec["action"]
    task_key = task_spec["id"]
    raw_input = task_spec.get("input", {}) or {}
    resolved_input = _substitute_refs(raw_input, outputs)
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

        # Set per-worker trace context so its LLM calls log as children.
        worker_ctx = tracing.TraceContext(
            company_id=company_id, session_id=session_id,
            parent_span_id=None,    # could be the manager's span; left None for flat-ish view
            agent_name=agent_name,
        )
        token = None
        try:
            from app.cost.tracing import _current
            token = _current.set(worker_ctx)
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
        finally:
            if token is not None:
                from app.cost.tracing import _current
                _current.reset(token)

        outputs[task_key] = final_output or {}
        out_payload = outputs[task_key] if isinstance(outputs[task_key], dict) else {"value": outputs[task_key]}
        task_queue.mark_ok(db, db_task_id, out_payload)
        await event_queue.put(WorkerEvent("status", agent_name,
                                           {"task_key": task_key, "status": "ok"}, task_key))
    finally:
        db.close()


async def _execute_dag(tasks, db_task_ids, event_queue, company_id, session_id):
    outputs = {}
    remaining = {t["id"]: t for t in tasks}
    in_flight = {}

    while remaining or in_flight:
        for tid in list(remaining.keys()):
            t = remaining[tid]
            if all(d in outputs for d in (t.get("depends_on") or [])):
                fut = asyncio.create_task(
                    _run_one_task(t, db_task_ids[tid], outputs, event_queue,
                                  company_id, session_id)
                )
                in_flight[tid] = fut
                del remaining[tid]
        if not in_flight:
            for tid, t in remaining.items():
                await event_queue.put(WorkerEvent("error", "manager",
                    f"Task {tid} skipped — unresolved deps: {t.get('depends_on')}", tid))
            break
        done, _ = await asyncio.wait(in_flight.values(), return_when=asyncio.FIRST_COMPLETED)
        for fut in done:
            for tid, f in list(in_flight.items()):
                if f is fut:
                    del in_flight[tid]; break

    return outputs


async def run_manager(session_id: int, user_message: str,
                      company_id: int, user_id: int) -> AsyncGenerator[dict, None]:
    """Run a manager turn. Sets the trace context for the duration."""
    # Set top-level trace context. Workers will swap their own in/out around it.
    manager_ctx = tracing.TraceContext(
        company_id=company_id, session_id=session_id,
        parent_span_id=None, agent_name="manager",
    )
    from app.cost.tracing import _current
    top_token = _current.set(manager_ctx)

    try:
        db = SessionLocal()
        try:
            db.add(AgentMessage(session_id=session_id, role="user", content=user_message))
            db.commit()
        finally:
            db.close()

        yield {"type": "manager_start", "agent": "manager", "content": "Planning..."}

        sys_prompt = PLAN_SYSTEM_PROMPT.format(capabilities=registry.capabilities_prompt())
        plan_result = await route_llm(sys_prompt, user_message,
                                       tier="cheap", agent_name="manager")
        try:
            plan = parse_json_lenient(plan_result.content)
        except Exception as e:
            yield {"type": "error", "agent": "manager",
                   "content": f"Failed to parse plan: {e}\nRaw: {plan_result.content[:300]}"}
            return

        tasks = plan.get("tasks", []) or []
        reply_hint = plan.get("reply_hint", "")
        yield {"type": "plan", "agent": "manager",
               "content": {"tasks": tasks, "reply_hint": reply_hint,
                           "_router": {"model": plan_result.model_used,
                                       "cost_usd": plan_result.cost_usd,
                                       "cache_hit": plan_result.was_cache_hit}}}

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

        # Persist tasks
        db_task_ids = {}
        db = SessionLocal()
        try:
            for t in tasks:
                tid = task_queue.create_task(
                    db, session_id=session_id, task_key=t["id"],
                    agent_name=t["agent"], action=t["action"],
                    input_json=t.get("input") or {},
                    depends_on=t.get("depends_on") or [],
                )
                db_task_ids[t["id"]] = tid
        finally:
            db.close()

        # Execute
        event_queue = asyncio.Queue()

        async def runner():
            try:
                outs = await _execute_dag(tasks, db_task_ids, event_queue,
                                          company_id, session_id)
                await event_queue.put({"__final__": outs})
            except Exception as e:
                await event_queue.put(WorkerEvent("error", "manager", str(e)))
                await event_queue.put({"__final__": {}})

        runner_task = asyncio.create_task(runner())
        final_outputs = None
        while True:
            item = await event_queue.get()
            if isinstance(item, dict) and "__final__" in item:
                final_outputs = item["__final__"]; break
            if isinstance(item, WorkerEvent):
                yield item.to_dict()
            else:
                yield item
        await runner_task

        # Aggregate
        yield {"type": "aggregating", "agent": "manager", "content": "Synthesizing reply..."}
        summary_input = {
            "user_message": user_message,
            "reply_hint": reply_hint,
            "task_outputs": final_outputs or {},
        }
        agg_tier = "standard"
        db_plan = SessionLocal()
        try:
            plan = get_company_plan(db_plan, company_id)
            agg_tier = resolve_manager_aggregate_tier(plan)
        finally:
            db_plan.close()

        agg_result = await route_llm(
            AGGREGATE_SYSTEM_PROMPT,
            json.dumps(summary_input, default=str)[:8000],
            tier=agg_tier, agent_name="manager",
        )
        reply = agg_result.content.strip()

        db = SessionLocal()
        try:
            db.add(AgentMessage(session_id=session_id, role="manager", content=reply,
                                metadata_json={"task_count": len(tasks),
                                                "router": {
                                                    "model": agg_result.model_used,
                                                    "cost_usd": agg_result.cost_usd,
                                                    "cache_hit": agg_result.was_cache_hit,
                                                }}))
            db.commit()
        finally:
            db.close()

        yield {"type": "manager_reply", "agent": "manager", "content": reply,
               "_router": {"model": agg_result.model_used,
                           "cost_usd": agg_result.cost_usd,
                           "cache_hit": agg_result.was_cache_hit,
                           "was_downgraded": agg_result.was_downgraded,
                           "was_plan_limited": agg_result.was_plan_limited,
                           "tier_requested": agg_tier}}
    finally:
        _current.reset(top_token)
