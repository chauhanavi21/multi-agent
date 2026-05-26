"""Task queue helpers — every manager-generated subtask flows through this.

Tasks live in the `tasks` table created by migrate_phase2. This module wraps
CRUD so the manager doesn't sprinkle SQLAlchemy everywhere.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.migrate_phase2 import Task


def create_task(db: Session, session_id: int, task_key: str, agent_name: str,
                action: str, input_json: dict, depends_on: list[str] | None = None) -> int:
    t = Task(
        session_id=session_id,
        task_key=task_key,
        agent_name=agent_name,
        action=action,
        input_json=input_json or {},
        depends_on=depends_on or [],
        status="pending",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t.id


def mark_running(db: Session, task_id: int):
    t = db.query(Task).get(task_id)
    if t:
        t.status = "running"
        t.started_at = datetime.utcnow()
        db.commit()


def mark_ok(db: Session, task_id: int, output: dict):
    t = db.query(Task).get(task_id)
    if t:
        t.status = "ok"
        t.output_json = output
        t.finished_at = datetime.utcnow()
        db.commit()


def mark_error(db: Session, task_id: int, error: str):
    t = db.query(Task).get(task_id)
    if t:
        t.status = "error"
        t.error = error
        t.finished_at = datetime.utcnow()
        db.commit()


def list_tasks_for_session(db: Session, session_id: int):
    rows = db.query(Task).filter(Task.session_id == session_id).order_by(Task.id).all()
    return [
        {
            "id": r.id, "task_key": r.task_key, "agent_name": r.agent_name,
            "action": r.action, "input": r.input_json, "output": r.output_json,
            "depends_on": r.depends_on or [], "status": r.status, "error": r.error,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in rows
    ]
