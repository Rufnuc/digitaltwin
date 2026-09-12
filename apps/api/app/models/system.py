from __future__ import annotations

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AlertSeverity
from app.db.base import Base, TimestampMixin


class AuditLog(Base, TimestampMixin):
    """Immutable trail of important operations, including AI actions (spec §36)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="api")
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    severity: Mapped[str] = mapped_column(String(16), default=AlertSeverity.INFO.value, index=True)
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # DEMO alerts must be distinguishable from ones raised by real analytics.
    data_origin: Mapped[str] = mapped_column(String(32), default="REAL", index=True)


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    # user_id NULL = broadcast (visible to everyone in this single-business app).
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="general", index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)  # in-app path
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
