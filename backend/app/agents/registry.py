"""Single source of truth for which agents exist.

The manager reads `capabilities_prompt()` to know what's available when planning.
"""
from app.agents.sales_agent import SalesWorker
from app.agents.dev_backend import BackendDevWorker
from app.agents.dev_frontend import FrontendDevWorker
from app.agents.dev_qa import QAWorker
from app.agents.social_analyst import SocialAnalystWorker


_WORKERS = {
    w.spec.name: w for w in [
        SalesWorker(),
        BackendDevWorker(),
        FrontendDevWorker(),
        QAWorker(),
        SocialAnalystWorker(),
    ]
}


def get_worker(name: str):
    return _WORKERS.get(name)


def list_workers():
    return list(_WORKERS.values())


def capabilities_prompt() -> str:
    """Human-readable summary for the manager LLM."""
    lines = []
    for w in _WORKERS.values():
        s = w.spec
        lines.append(f"- {s.name} ({s.display_name}): {s.capabilities}")
    return "\n".join(lines)


def org_chart():
    """Structured info for the UI."""
    return [
        {
            "name": w.spec.name,
            "display_name": w.spec.display_name,
            "description": w.spec.description,
            "actions": w.spec.actions,
        }
        for w in _WORKERS.values()
    ]
