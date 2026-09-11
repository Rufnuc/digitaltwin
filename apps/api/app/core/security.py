"""Password hashing, JWT issuance, and RBAC helpers (spec §37)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.enums import ROLE_ORDER, Role

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_access_token(subject: str, role: str, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.AUTH_SECRET, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.AUTH_SECRET, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def role_at_least(actual: Role | str, required: Role | str) -> bool:
    """True if `actual` is at least as privileged as `required` (hierarchical)."""
    actual = Role(actual)
    required = Role(required)
    return ROLE_ORDER.index(actual) >= ROLE_ORDER.index(required)
