from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, Role
from app.core.security import (
    create_access_token,
    hash_password,
    role_rank,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, Token, UserCreate, UserOut, UserUpdate
from app.services import audit

router = APIRouter(tags=["auth"])


def _active_owner_count(db: Session, exclude_id: int | None = None) -> int:
    from sqlalchemy import func

    stmt = select(func.count()).select_from(User).where(
        User.role == Role.OWNER.value, User.is_active.is_(True)
    )
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return int(db.scalar(stmt) or 0)


@router.post("/auth/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(db_session)) -> Token:
    from datetime import datetime, timedelta, timezone

    from app.core.config import settings

    now = datetime.now(timezone.utc)
    user = db.scalar(select(User).where(User.email == payload.email))

    # Account lockout: while locked, refuse even a correct password (don't reset the
    # timer). Unknown emails get the same generic 401 to avoid user enumeration.
    if user is not None and user.lockout_until is not None:
        locked_until = user.lockout_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many failed attempts. Try again later.",
            )

    if user is None or not verify_password(payload.password, user.hashed_password):
        if user is not None:
            # Count the failure and lock the account once the threshold is crossed.
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= settings.LOGIN_MAX_ATTEMPTS:
                user.lockout_until = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
                audit.record(db, action=AuditAction.LOGIN, user_id=user.id,
                             summary=f"account locked after {user.failed_login_count} "
                                     f"failed logins: {user.email}")
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is inactive")

    # Device binding: a device-locked account (and any SALESGIRL) may only sign in
    # from an approved device. A new device is recorded PENDING and refused here.
    from app.services import devices
    try:
        devices.check_login_device(db, user, payload.device_id, payload.device_label)
    except devices.DeviceError as e:
        audit.record(db, action=AuditAction.LOGIN, user_id=user.id,
                     summary=f"device-blocked login ({e.code}): {user.email}")
        raise HTTPException(status.HTTP_403_FORBIDDEN, e.message) from None

    # Success: clear any failure state.
    if user.failed_login_count or user.lockout_until:
        user.failed_login_count = 0
        user.lockout_until = None
        db.commit()
    audit.record(db, action=AuditAction.LOGIN, user_id=user.id, summary=f"login {user.email}")
    token = create_access_token(subject=str(user.id), role=user.role)
    return Token(access_token=token, role=user.role)


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/auth/refresh", response_model=Token)
def refresh(user: User = Depends(get_current_user)) -> Token:
    """Re-issue a fresh access token for the current (still-valid) session.

    A sliding session: while the user is active and refreshes before expiry, they
    stay logged in; an expired token cannot be refreshed and requires a new login.
    """
    token = create_access_token(subject=str(user.id), role=user.role)
    return Token(access_token=token, role=user.role)


@router.post("/auth/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(db_session),
    admin: User = Depends(require_role(Role.ADMIN)),
) -> User:
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    Role(payload.role)  # validate role string
    # Privilege-escalation guard: you cannot create a user more privileged than
    # yourself, and only an OWNER may appoint another OWNER.
    if role_rank(payload.role) > role_rank(admin.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "You cannot create a user with a role higher than your own")
    if payload.role == Role.OWNER.value and admin.role != Role.OWNER.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Only an OWNER can create another OWNER")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/auth/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ADMIN)),
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)).all())


@router.patch("/auth/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(db_session),
    admin: User = Depends(require_role(Role.ADMIN)),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    changes = payload.model_dump(exclude_unset=True)
    if "role" in changes and changes["role"] is not None:
        new_role = changes["role"]
        Role(new_role)  # validate
        # Privilege-escalation guards:
        if user.id == admin.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "You cannot change your own role")
        if role_rank(new_role) > role_rank(admin.role):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "You cannot grant a role higher than your own")
        if new_role == Role.OWNER.value and admin.role != Role.OWNER.value:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Only an OWNER can appoint another OWNER")
        # Last-OWNER protection: don't demote the only remaining active owner.
        if (user.role == Role.OWNER.value and new_role != Role.OWNER.value
                and _active_owner_count(db, exclude_id=user.id) == 0):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Cannot remove the last remaining OWNER")
        user.role = new_role
    if "full_name" in changes and changes["full_name"] is not None:
        user.full_name = changes["full_name"]
    if "email" in changes and changes["email"] is not None:
        new_email = str(changes["email"]).strip().lower()
        # Only change the login email of yourself or a lower-privileged user, and
        # keep emails unique.
        if user.id != admin.id and role_rank(user.role) >= role_rank(admin.role):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "You cannot change the email of a user at your level or higher",
            )
        clash = db.scalar(select(User).where(User.email == new_email, User.id != user.id))
        if clash is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "That email is already in use")
        user.email = new_email
    if "is_active" in changes and changes["is_active"] is not None:
        # Don't let an admin lock themselves out.
        if user.id == admin.id and changes["is_active"] is False:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself")
        # Can't deactivate a user more privileged than yourself.
        if (changes["is_active"] is False and user.id != admin.id
                and role_rank(user.role) > role_rank(admin.role)):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "You cannot deactivate a user more privileged than yourself")
        # Last-OWNER protection: don't deactivate the only remaining active owner.
        if (changes["is_active"] is False and user.role == Role.OWNER.value
                and _active_owner_count(db, exclude_id=user.id) == 0):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Cannot deactivate the last remaining OWNER")
        user.is_active = changes["is_active"]
    if changes.get("password"):
        # Password-reset guard: you may reset your own password, but not that of a
        # user at an equal-or-higher privilege level (that would be account takeover).
        if user.id != admin.id and role_rank(user.role) >= role_rank(admin.role):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "You cannot reset the password of a user at your level or higher",
            )
        user.hashed_password = hash_password(changes["password"])
    if "device_locked" in changes and changes["device_locked"] is not None:
        user.device_locked = changes["device_locked"]
    db.commit()
    db.refresh(user)
    audit.record(db, action=AuditAction.UPDATE, user_id=admin.id, entity_type="user",
                 entity_id=user.id, summary=f"updated user {user.email}")
    return user


# ---- Device binding management (admin/owner) ----

@router.get("/auth/users/{user_id}/devices")
def user_devices(
    user_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ADMIN)),
) -> dict:
    from app.services import devices
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {"items": devices.list_devices(db, user_id)}


class DeviceStatusIn(BaseModel):
    status: str  # APPROVED | BLOCKED | PENDING


@router.patch("/auth/users/{user_id}/devices/{device_pk}")
def set_device_status(
    user_id: int,
    device_pk: int,
    payload: DeviceStatusIn,
    db: Session = Depends(db_session),
    admin: User = Depends(require_role(Role.ADMIN)),
) -> dict:
    from app.services import devices
    r = devices.set_status(db, user_id, device_pk, payload.status, admin.id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    if "error" in r:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, r["error"])
    audit.record(db, action=AuditAction.UPDATE, user_id=admin.id, entity_type="user_device",
                 entity_id=device_pk, summary=f"device {payload.status} for user {user_id}")
    return r


@router.delete("/auth/users/{user_id}/devices/{device_pk}",
               status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def remove_device(
    user_id: int,
    device_pk: int,
    db: Session = Depends(db_session),
    admin: User = Depends(require_role(Role.ADMIN)),
) -> Response:
    from app.services import devices
    if not devices.delete_device(db, user_id, device_pk):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    audit.record(db, action=AuditAction.DELETE, user_id=admin.id, entity_type="user_device",
                 entity_id=device_pk, summary=f"removed device for user {user_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
