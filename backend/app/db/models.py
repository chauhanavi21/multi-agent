from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    title = Column(String(120), nullable=False)
    company = Column(String(120), nullable=False)
    industry = Column(String(80))
    email = Column(String(160), unique=True, nullable=False)
    notes = Column(Text)
    status = Column(String(40), default="new")     # new, contacted, replied, lost
    created_at = Column(DateTime, default=datetime.utcnow)

    emails = relationship("EmailDraft", back_populates="lead", cascade="all, delete")


class EmailDraft(Base):
    __tablename__ = "email_drafts"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    subject = Column(String(240), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(40), default="draft")   # draft, sent, queued
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    lead = relationship("Lead", back_populates="emails")


class AgentRun(Base):
    """Tracks every agent execution for replay + future multi-agent tracing."""
    __tablename__ = "agent_runs"
    id = Column(Integer, primary_key=True)
    agent_name = Column(String(60), nullable=False)
    parent_run_id = Column(Integer, ForeignKey("agent_runs.id"), nullable=True)
    input_payload = Column(Text)
    output_payload = Column(Text)
    status = Column(String(40), default="running") # running, ok, error
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
