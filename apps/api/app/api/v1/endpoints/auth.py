from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, Role
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, Token, UserCreate, UserOut, UserUpdate
from app.services import audit

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(db_session)) -> Token:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is inactive")
    audit.record(db, action=AuditAction.LOGIN, user_id=user.id, summary=f"login {user.email}")
    token = create_access_token(subject=str(user.id), role=user.role)
    return Token(access_token=token, role=user.role)


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/auth/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ADMIN)),
) -> User:
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    Role(payload.role)  # validate role string
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
        Role(changes["role"])  # validate
        user.role = changes["role"]
    if "full_name" in changes and changes["full_name"] is not None:
        user.full_name = changes["full_name"]
    if "is_active" in changes and changes["is_active"] is not None:
        # Don't let an admin lock themselves out.
        if user.id == admin.id and changes["is_active"] is False:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself")
        user.is_active = changes["is_active"]
    if changes.get("password"):
        user.hashed_password = hash_password(changes["password"])
    db.commit()
    db.refresh(user)
    audit.record(db, action=AuditAction.UPDATE, user_id=admin.id, entity_type="user",
                 entity_id=user.id, summary=f"updated user {user.email}")
    return user
