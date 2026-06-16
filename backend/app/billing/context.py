"""Request-scoped billing context (scheduler runs, etc.)."""
from __future__ import annotations
import contextvars
from contextlib import contextmanager

_scheduled = contextvars.ContextVar("_scheduled", default=False)


def is_scheduled_run() -> bool:
    return bool(_scheduled.get())


@contextmanager
def scheduled_run():
    token = _scheduled.set(True)
    try:
        yield
    finally:
        _scheduled.reset(token)
