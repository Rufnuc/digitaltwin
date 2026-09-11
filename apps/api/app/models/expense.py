from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ProvenanceMixin, TimestampMixin
from app.models.organization import MONEY


class Expense(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    amount: Mapped[float] = mapped_column(MONEY, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
