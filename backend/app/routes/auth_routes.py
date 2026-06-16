"""Auth routes — signup, login, get current user."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.db.migrate_phase3 import User, Company, CompanyMember
from app.billing.plans import apply_plan_to_company, plan_summary
from app.auth.security import hash_password, verify_password, create_access_token
from app.auth.deps import get_current_user


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _company_payload(c: Company) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "plan": plan_summary(getattr(c, "plan", None) or "free"),
    }


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=100)
    full_name: str = Field(default="", max_length=160)
    company_name: str = Field(min_length=1, max_length=160)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    company: dict | None


@router.post("/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(409, "Email already registered")

    # Create user first (without company), then company, then link.
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    db.flush()    # get user.id without committing

    company = Company(name=payload.company_name, owner_user_id=user.id)
    apply_plan_to_company(company, "free")
    db.add(company)
    db.flush()

    user.company_id = company.id
    db.add(CompanyMember(user_id=user.id, company_id=company.id, role="owner"))
    db.commit()
    db.refresh(user)
    db.refresh(company)

    token = create_access_token(user.id, user.is_admin, user.company_id)
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "full_name": user.full_name,
              "is_admin": user.is_admin, "company_id": user.company_id},
        company=_company_payload(company),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "Account is inactive")

    user.last_login_at = datetime.utcnow()
    db.commit()

    company = None
    if user.company_id:
        c = db.query(Company).filter(Company.id == user.company_id).first()
        if c:
            company = _company_payload(c)

    token = create_access_token(user.id, user.is_admin, user.company_id)
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "full_name": user.full_name,
              "is_admin": user.is_admin, "company_id": user.company_id},
        company=company,
    )


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = None
    if user.company_id:
        c = db.query(Company).filter(Company.id == user.company_id).first()
        if c:
            company = _company_payload(c)
    return {
        "user": {
            "id": user.id, "email": user.email, "full_name": user.full_name,
            "is_admin": user.is_admin, "company_id": user.company_id,
        },
        "company": company,
    }
