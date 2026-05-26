"""Phase 2 migration — additive only.

Adds:
  - chat_sessions    (top-level user conversations)
  - agent_messages   (chat history within a session)
  - tasks            (manager-generated work units)

Does NOT touch Phase 1 tables (leads, email_drafts, agent_runs).

Run with: python -m app.db.migrate_phase2
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, Index,
)
from sqlalchemy.orm import relationship
from app.db.models import Base, engine


# --- new tables ---

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), default="Untitled")
    user_id = Column(Integer, nullable=True)        # filled in Phase 3
    company_id = Column(Integer, nullable=True)     # filled in Phase 3
    created_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship("AgentMessage", back_populates="session",
                            cascade="all, delete", order_by="AgentMessage.id")
    tasks = relationship("Task", back_populates="session", cascade="all, delete")


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(40), nullable=False)       # user, manager, agent, system
    agent_name = Column(String(60), nullable=True)  # filled when role=agent
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    task_key = Column(String(40), nullable=False)   # e.g. "t1"
    agent_name = Column(String(60), nullable=False)
    action = Column(String(80), nullable=False)
    input_json = Column(JSON, nullable=True)
    output_json = Column(JSON, nullable=True)
    depends_on = Column(JSON, nullable=True)        # list of task_keys
    status = Column(String(20), default="pending")  # pending, running, ok, error, skipped
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="tasks")


Index("ix_tasks_session_status", Task.session_id, Task.status)
Index("ix_messages_session", AgentMessage.session_id)


def main():
    print("Creating Phase 2 tables (additive, won't touch Phase 1 data)...")
    Base.metadata.create_all(bind=engine, tables=[
        ChatSession.__table__,
        AgentMessage.__table__,
        Task.__table__,
    ])
    print("Done. Tables created: chat_sessions, agent_messages, tasks.")


if __name__ == "__main__":
    main()
