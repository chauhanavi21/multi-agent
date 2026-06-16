"""Agent registry — Phase 6 adds ceo, insights, outreach."""
from __future__ import annotations
from app.agents.sales_agent import SalesWorker
from app.agents.dev_backend import BackendDevWorker
from app.agents.dev_frontend import FrontendDevWorker
from app.agents.dev_qa import QAWorker
from app.agents.social_analyst import SocialAnalystWorker
from app.agents.ceo import CEOWorker
from app.agents.insights import InsightsWorker
from app.agents.outreach import OutreachWorker


_WORKERS = {}


def _register(worker_cls):
    w = worker_cls()
    _WORKERS[w.spec.name] = w
    return w


_register(SalesWorker)
_register(BackendDevWorker)
_register(FrontendDevWorker)
_register(QAWorker)
_register(SocialAnalystWorker)
_register(CEOWorker)
_register(InsightsWorker)
_register(OutreachWorker)


def get_worker(name: str):
    return _WORKERS.get(name)


def list_workers():
    return list(_WORKERS.values())


def org_chart():
    return [
        {
            "name": w.spec.name,
            "display_name": w.spec.display_name,
            "description": w.spec.description,
            "actions": w.spec.actions,
        }
        for w in _WORKERS.values()
    ]


def capabilities_prompt() -> str:
    """A compact list of agents + actions to inject into the manager's system prompt."""
    lines = []
    for w in _WORKERS.values():
        lines.append(f"- {w.spec.name}: {w.spec.capabilities}")
    return "\n".join(lines)
