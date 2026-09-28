"""Shared API dependencies: DB session, current user, and RBAC guards."""
from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.core.security import decode_access_token, role_at_least
from app.db.session import get_db
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


def db_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(db_session),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    # Tag the session so the automatic audit trail attributes changes to this user.
    # Stored on the session (not a contextvar) so it survives FastAPI's threading.
    from app.services.audit_listener import ACTOR_KEY
    db.info[ACTOR_KEY] = user.id
    return user


def require_role(minimum: Role, *, allow: tuple[Role, ...] = ()):
    """Dependency factory enforcing a minimum role (hierarchical).

    ``allow`` whitelists specific roles that don't meet the hierarchy but are
    permitted on this endpoint anyway — used to grant the restricted SALESGIRL
    role the handful of actions it needs (invoices, waybills, customer adds/payments)
    without lifting it above STAFF everywhere.
    """
    allowed = {r.value for r in allow}

    def _guard(user: User = Depends(get_current_user)) -> User:
        if not (role_at_least(user.role, minimum) or user.role in allowed):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires role {minimum.value} or higher (you are {user.role}).",
            )
        return user

    return _guard
