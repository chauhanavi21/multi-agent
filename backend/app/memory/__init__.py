"""Shared memory system.

Auto-detects backend on first use:
  - pgvector if the extension is installed
  - numpy in-process otherwise (always-works fallback)

Public API:
    from app.memory import store
    store.remember(company_id, kind, content, ...)
    store.retrieve(company_id, query, k=5, ...)
    store.list_recent(company_id, limit=50)
    store.delete(company_id, memory_id)
"""
from app.memory.store import (
    remember, retrieve, list_recent, delete,
    update_importance, get_backend_mode,
    compress_observation_to_memory,
)

__all__ = [
    "remember", "retrieve", "list_recent", "delete",
    "update_importance", "get_backend_mode",
    "compress_observation_to_memory",
]
