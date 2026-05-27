"""One-time bootstrap: create the default boss admin.

Run: python -m app.db.bootstrap_admin
"""
from app.config import settings
from app.db.models import SessionLocal
from app.db.migrate_phase3 import User
from app.auth.security import hash_password


def main():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == settings.bootstrap_admin_email).first()
        if existing:
            print(f"Admin user {settings.bootstrap_admin_email} already exists (id={existing.id}).")
            print(f"is_admin={existing.is_admin}, is_active={existing.is_active}")
            return

        admin = User(
            email=settings.bootstrap_admin_email,
            full_name="Boss",
            password_hash=hash_password(settings.bootstrap_admin_password),
            is_admin=True,
            is_active=True,
            company_id=None,    # admin has no company; bypass isolation
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"Created admin: {admin.email} (id={admin.id})")
        print(f"Password: {settings.bootstrap_admin_password}  (change after first login)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
