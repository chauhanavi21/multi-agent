"""SMS sending.

If TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_FROM_NUMBER are set:
  the message is sent via the Twilio REST API (lazy-imported).
Otherwise:
  the message is stored in sms_outbox with status='mock'.

Either way the message goes into sms_outbox so the UI can show it.
"""
from __future__ import annotations
import logging
from datetime import datetime

from app.config import settings
from app.db.models import SessionLocal

log = logging.getLogger(__name__)


def _has_twilio_config() -> bool:
    return bool(
        settings.twilio_account_sid and settings.twilio_auth_token
        and settings.twilio_from_number
    )


def queue_sms(company_id: int, to_number: str, body: str,
              lead_id: int | None = None) -> dict:
    """Queue an SMS and (optionally) send it. Returns metadata about the result."""
    from app.db.migrate_phase6 import SmsOutbox

    db = SessionLocal()
    try:
        row = SmsOutbox(
            company_id=company_id, lead_id=lead_id,
            to_number=to_number[:40], body=body[:1600],
            status="queued",
        )
        db.add(row); db.commit(); db.refresh(row)
        sms_id = row.id

        if not _has_twilio_config():
            row.status = "mock"
            row.sent_at = datetime.utcnow()
            db.commit()
            return {
                "ok": True, "sms_id": sms_id, "status": "mock",
                "to": to_number, "body": body,
                "note": "TWILIO_* not configured — message stored only",
            }

        # Real send (lazy-import)
        try:
            from twilio.rest import Client
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            msg = client.messages.create(
                body=body,
                from_=settings.twilio_from_number,
                to=to_number,
            )
            row.status = "sent"
            row.twilio_sid = msg.sid
            row.sent_at = datetime.utcnow()
            db.commit()
            return {"ok": True, "sms_id": sms_id, "status": "sent", "twilio_sid": msg.sid}
        except Exception as e:
            row.status = "failed"
            row.error = str(e)[:500]
            db.commit()
            log.warning("twilio send failed: %s", e)
            return {"ok": False, "sms_id": sms_id, "status": "failed", "error": str(e)}
    finally:
        db.close()


def list_sms(company_id: int, limit: int = 50) -> list[dict]:
    from app.db.migrate_phase6 import SmsOutbox
    db = SessionLocal()
    try:
        rows = db.query(SmsOutbox).filter(
            SmsOutbox.company_id == company_id
        ).order_by(SmsOutbox.id.desc()).limit(limit).all()
        return [
            {
                "id": r.id, "lead_id": r.lead_id, "to_number": r.to_number,
                "body": r.body, "status": r.status, "error": r.error,
                "twilio_sid": r.twilio_sid,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()
