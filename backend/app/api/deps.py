from __future__ import annotations

import uuid
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import decode_token
from app.database import get_db
from app.models import User


def db_session() -> Iterator[Session]:
    yield from get_db()


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(db_session),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token.")
    payload = decode_token(authorization.split(" ", 1)[1].strip())
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.")
    user = db.scalars(_user_query(payload["sub"])).first()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is not active.")
    return user


def _user_query(email: str):
    from sqlalchemy import select

    return select(User).where(User.email == email)


def require_role(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if roles and user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires one of: {', '.join(roles)}")
        return user

    return dependency


def parse_uuid(value: str, field: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid {field}.") from None
