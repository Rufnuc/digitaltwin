from __future__ import annotations

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EntityStatus
from app.db.base import Base, ProvenanceMixin, TimestampMixin


class Supplier(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="NGN")
    payment_terms: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 0..1 reliability score; nullable until enough delivery history exists.
    reliability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=EntityStatus.ACTIVE.value, index=True)
