from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session
from app.auth import create_token, verify_password
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


def _serialize(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "store_id": str(user.store_id) if user.store_id else None,
    }


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(db_session)) -> dict:
    user = db.scalars(select(User).where(User.email == payload.email)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled.")
    token = create_token(user.email, user.role, str(user.store_id) if user.store_id else None)
    return {"token": token, "user": _serialize(user)}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return _serialize(user)
