from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, ProvenanceMixin, TimestampMixin
from app.models.organization import MONEY


class Purchase(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id"), index=True, nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    subtotal: Mapped[float] = mapped_column(MONEY, default=0)
    tax: Mapped[float] = mapped_column(MONEY, default=0)
    total: Mapped[float] = mapped_column(MONEY, default=0)

    lines: Mapped[list[PurchaseLine]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan"
    )


class PurchaseLine(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "purchase_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id"), index=True, nullable=False
    )
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    original_description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    unit_cost: Mapped[float] = mapped_column(MONEY, default=0)
    line_total: Mapped[float] = mapped_column(MONEY, default=0)

    purchase: Mapped[Purchase] = relationship(back_populates="lines")
