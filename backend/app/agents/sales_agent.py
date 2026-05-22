"""Sales agent built as a LangGraph state machine.

Flow:
  start → plan → execute → finalize → end

Each node yields events that get streamed to the frontend via SSE.
This same pattern scales to multi-agent in Phase 2: add a 'route' node
that picks which specialist handles the task.
"""
import json
from typing import TypedDict, Literal, Optional
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from app.config import settings
from app.db.models import SessionLocal
from app.tools import lead_tools, email_tools


# ----- state -----

class AgentState(TypedDict, total=False):
    task: Literal["draft_email", "generate_leads"]
    lead_id: Optional[int]
    criteria: Optional[str]
    plan: str
    result: dict
    events: list   # streamed back to UI


# ----- LLM -----

def get_llm():
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=settings.ollama_temperature,
    )


# ----- nodes -----

def plan_node(state: AgentState) -> AgentState:
    """Ask the LLM to plan what it will do for this task."""
    llm = get_llm()
    task = state["task"]
    if task == "draft_email":
        prompt = (
            f"You are a B2B sales agent. You will draft a personalized cold email "
            f"for lead_id={state['lead_id']}. In ONE short sentence, state your plan."
        )
    else:
        prompt = (
            f"You are a sales agent. You will generate 3 fictional but realistic "
            f"B2B leads matching: '{state.get('criteria', 'any industry')}'. "
            f"In ONE short sentence, state your plan."
        )
    msg = llm.invoke([SystemMessage(content="Be terse."), HumanMessage(content=prompt)])
    plan = msg.content.strip()
    events = state.get("events", []) + [{"type": "plan", "content": plan}]
    return {**state, "plan": plan, "events": events}


def execute_node(state: AgentState) -> AgentState:
    """Run the actual tool work."""
    if state["task"] == "draft_email":
        return _execute_draft_email(state)
    return _execute_generate_leads(state)


def _execute_draft_email(state: AgentState) -> AgentState:
    events = state.get("events", [])
    db = SessionLocal()
    try:
        lead = lead_tools.get_lead(db, state["lead_id"])
        if not lead:
            events.append({"type": "error", "content": f"Lead {state['lead_id']} not found"})
            return {**state, "result": {"ok": False}, "events": events}

        events.append({"type": "tool", "content": f"Loaded lead: {lead['name']} ({lead['company']})"})

        llm = get_llm()
        system = (
            "You write concise, personalized B2B cold emails. "
            "Rules: under 120 words; one clear ask; reference the lead's notes; "
            "no fluff, no 'I hope this email finds you well'. "
            "Output strictly as JSON: {\"subject\": \"...\", \"body\": \"...\"}. "
            "No markdown, no code fences, just the raw JSON object."
        )
        user = (
            f"Lead: {lead['name']}, {lead['title']} at {lead['company']} "
            f"({lead['industry']}).\nNotes: {lead['notes']}\n"
            f"We sell a developer-focused agent platform that automates outbound + ops. "
            f"Write the email."
        )
        events.append({"type": "thinking", "content": "Drafting email..."})

        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        raw = resp.content.strip()

        # robust JSON extraction (some models wrap in ```json fences)
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # fallback: split heuristically
            parsed = {"subject": "Quick question about " + lead["company"], "body": raw}

        draft_id = email_tools.save_draft(db, lead["id"], parsed["subject"], parsed["body"])

        events.append({
            "type": "draft_ready",
            "content": {
                "draft_id": draft_id,
                "lead_id": lead["id"],
                "subject": parsed["subject"],
                "body": parsed["body"],
            },
        })
        return {**state, "result": {"ok": True, "draft_id": draft_id}, "events": events}
    finally:
        db.close()


def _execute_generate_leads(state: AgentState) -> AgentState:
    events = state.get("events", [])
    criteria = state.get("criteria", "B2B SaaS companies")
    db = SessionLocal()
    try:
        events.append({"type": "tool", "content": f"Generating 3 leads for: {criteria}"})
        llm = get_llm()
        system = (
            "Generate exactly 3 fictional but realistic B2B leads. "
            "Output strictly a JSON array: "
            "[{\"name\":\"\",\"title\":\"\",\"company\":\"\",\"industry\":\"\",\"email\":\"\",\"notes\":\"\"}]. "
            "Emails must use the .example domain. No markdown, no code fences."
        )
        user = f"Criteria: {criteria}"
        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        raw = resp.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        try:
            arr = json.loads(raw)
        except json.JSONDecodeError:
            events.append({"type": "error", "content": "LLM returned non-JSON; retry."})
            return {**state, "result": {"ok": False}, "events": events}

        created = []
        for row in arr[:3]:
            try:
                nid = lead_tools.add_lead(db, row)
                created.append({**row, "id": nid})
            except Exception as e:
                events.append({"type": "error", "content": f"Skipped duplicate or bad lead: {e}"})
                db.rollback()

        events.append({"type": "leads_created", "content": created})
        return {**state, "result": {"ok": True, "created": created}, "events": events}
    finally:
        db.close()


def finalize_node(state: AgentState) -> AgentState:
    events = state.get("events", []) + [{"type": "done", "content": state.get("result", {})}]
    return {**state, "events": events}


# ----- graph -----

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan", plan_node)
    g.add_node("execute", execute_node)
    g.add_node("finalize", finalize_node)
    g.set_entry_point("plan")
    g.add_edge("plan", "execute")
    g.add_edge("execute", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


GRAPH = build_graph()


def run_agent(task: str, lead_id: Optional[int] = None, criteria: Optional[str] = None):
    """Run the agent and yield events one by one for SSE."""
    state: AgentState = {"task": task, "events": []}
    if lead_id is not None:
        state["lead_id"] = lead_id
    if criteria is not None:
        state["criteria"] = criteria

    last_emitted = 0
    for step in GRAPH.stream(state):
        # step is {node_name: state_dict}
        for _, partial in step.items():
            events = partial.get("events", [])
            for ev in events[last_emitted:]:
                yield ev
            last_emitted = len(events)
