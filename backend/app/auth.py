"""Local demo authentication.

Deliberately simple and dependency-free: PBKDF2-HMAC password hashing plus a compact
HMAC-SHA256 signed token. This is a hackathon demo identity layer, not an enterprise IdP.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid

from app.config import settings

_ITERATIONS = 120_000


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or base64.b16encode(os.urandom(16)).decode()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, encoded = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(base64.b64encode(digest).decode(), encoded)
    except Exception:
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(subject: str, role: str, store_id: str | None = None, ttl_minutes: int | None = None) -> str:
    payload = {
        "sub": subject,
        "role": role,
        "sid": store_id,
        "exp": int(time.time()) + (ttl_minutes or settings.token_ttl_minutes) * 60,
        "jti": uuid.uuid4().hex,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def decode_token(token: str) -> dict | None:
    try:
        body, signature = token.split(".")
        expected = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_unb64(signature), expected):
            return None
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None
