from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Role
from app.db.base import Base, TimestampMixin

# Device-binding statuses for user_devices.
DEVICE_STATUSES = ("PENDING", "APPROVED", "BLOCKED")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default=Role.VIEWER.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Brute-force protection: consecutive failed logins, and a lockout expiry.
    failed_login_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    lockout_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Device binding: when on, this user may only sign in from an approved device.
    # Always enforced for the SALESGIRL role regardless of this flag.
    device_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )


class UserDevice(Base, TimestampMixin):
    """A browser/device a user has signed in from. Device-locked accounts (and the
    SALESGIRL role) may only sign in from an APPROVED device; a new one lands as
    PENDING until an admin/owner approves it."""

    __tablename__ = "user_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Opaque id generated and stored by the browser (localStorage).
    device_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
