"""FastAPI dependencies for auth + company isolation.

Usage in routes:
    @app.get("/api/leads")
    def list_leads(user: User = Depends(get_current_user), ...):

    @app.get("/api/leads")
    def list_leads(ctx: CompanyContext = Depends(get_company_context), ...):
        # ctx.company_id is the scope; ctx.user is the user
"""
from dataclasses import dataclass
from typing import Optional
from fastapi import Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.db.migrate_phase3 import User, Company
from app.auth.security import decode_token


@dataclass
class CompanyContext:
    user: User
    company_id: int           # the scope for all queries
    company: Optional[Company]
    is_admin_override: bool   # True if admin viewed someone else's company


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the JWT into a User row."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header")
    token = authorization.split(None, 1)[1].strip()
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(401, "Invalid token payload")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(401, "User not found")
    if not user.is_active:
        raise HTTPException(403, "User is inactive")
    return user


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user


def get_company_context(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    company_id: Optional[int] = Query(None, description="Admin-only: view another company"),
) -> CompanyContext:
    """Resolve the company scope for the request.

    Regular users: always their own company.
    Admins: their own by default, OR can pass ?company_id= to view any company.
    """
    if user.is_admin and company_id is not None:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(404, f"Company {company_id} not found")
        return CompanyContext(user=user, company_id=company.id, company=company,
                              is_admin_override=True)

    if not user.company_id:
        # Admin with no own company — must specify ?company_id=
        if user.is_admin:
            raise HTTPException(400, "Admin must specify ?company_id= for company-scoped routes")
        raise HTTPException(403, "User has no company")

    company = db.query(Company).filter(Company.id == user.company_id).first()
    return CompanyContext(user=user, company_id=user.company_id, company=company,
                          is_admin_override=False)
