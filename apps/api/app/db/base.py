"""Declarative base and reusable column mixins.

Design notes:
- Types are kept portable (JSON not JSONB, string-backed enums) so the exact same
  models run on Postgres (app/prod) and SQLite (fast unit tests). Enum *values*
  are validated at the Pydantic layer; the DB stores the string.
- `ProvenanceMixin` realises spec §11/§49: every business record can declare how
  trustworthy it is and where it came from.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.enums import DataOrigin, VerificationStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


class ProvenanceMixin:
    """Epistemic metadata. Attached to imported/extracted business records.

    `data_origin` answers "should this be treated as fact?"; the remaining fields
    preserve the audit trail so uncertain source data is never silently trusted.
    """

    data_origin: Mapped[str] = mapped_column(
        String(32), default=DataOrigin.REAL.value, nullable=False, index=True
    )
    verification_status: Mapped[str] = mapped_column(
        String(32), default=VerificationStatus.VERIFIED.value, nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
