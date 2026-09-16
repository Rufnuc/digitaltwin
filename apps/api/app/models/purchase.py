from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
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
    currency: Mapped[str] = mapped_column(String(3), default="NGN")
    subtotal: Mapped[float] = mapped_column(MONEY, default=0)
    tax: Mapped[float] = mapped_column(MONEY, default=0)
    total: Mapped[float] = mapped_column(MONEY, default=0)

    # What we've paid the supplier so far (kept in step by the payables service).
    amount_paid: Mapped[float] = mapped_column(MONEY, default=0)
    payment_status: Mapped[str] = mapped_column(String(16), default="UNPAID", index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

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


class SupplierPayment(Base, TimestampMixin, ProvenanceMixin):
    """A payment we made to a supplier against a purchase (accounts payable)."""

    __tablename__ = "supplier_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id", ondelete="CASCADE"), index=True, nullable=False
    )
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id"), index=True, nullable=True
    )
    amount: Mapped[float] = mapped_column(MONEY, nullable=False)
    method: Mapped[str] = mapped_column(String(32), default="transfer")
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paid_at: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="CONFIRMED", index=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Bank-transfer traceability: money went FROM our account TO the supplier's.
    # from_* = our paying account; to_* = the supplier's receiving account.
    txid: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    from_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    to_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
