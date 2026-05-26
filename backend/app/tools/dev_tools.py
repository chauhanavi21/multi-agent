"""Tools for the dev agents.

Phase 2 deliberately does NOT execute code — agents produce specs, diffs,
and review notes. Code execution + sandboxing comes in Phase 4.
"""
from datetime import datetime


def make_spec_artifact(title: str, body: str) -> dict:
    """Wrap an LLM-produced spec/diff/note into a structured artifact."""
    return {
        "kind": "spec",
        "title": title,
        "body": body,
        "created_at": datetime.utcnow().isoformat(),
    }


def make_review_artifact(target: str, findings: list[str], severity: str = "info") -> dict:
    return {
        "kind": "review",
        "target": target,
        "severity": severity,
        "findings": findings,
        "created_at": datetime.utcnow().isoformat(),
    }
