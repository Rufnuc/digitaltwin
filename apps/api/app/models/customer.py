from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import CustomerType, EntityStatus
from app.db.base import Base, ProvenanceMixin, TimestampMixin
from app.models.organization import MONEY


class Customer(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_type: Mapped[str] = mapped_column(String(32), default=CustomerType.RETAIL.value)
    status: Mapped[str] = mapped_column(String(32), default=EntityStatus.ACTIVE.value, index=True)

    first_purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Summary rollups (materialised for performance; recomputed by analytics service).
    # Kept nullable so "not yet computed" is distinct from zero.
    lifetime_revenue: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    lifetime_gross_profit: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    order_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Credit terms for wholesale customers who buy on account.
    credit_limit: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    payment_terms_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
