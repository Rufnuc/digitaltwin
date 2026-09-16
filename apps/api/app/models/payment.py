"""Customer payments received against invoices (accounts receivable)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ProvenanceMixin, TimestampMixin
from app.models.organization import MONEY


class Payment(Base, TimestampMixin, ProvenanceMixin):
    """One payment a customer made towards an invoice. The invoice's amount_paid
    and payment_status are kept in step by the receivables service. A payment can
    be VOIDED (kept for the trail) rather than deleted."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Denormalised for fast per-customer receivables queries.
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), index=True, nullable=True
    )
    amount: Mapped[float] = mapped_column(MONEY, nullable=False)
    # cash | transfer | pos | opay | moniepoint | cheque | other
    method: Mapped[str] = mapped_column(String(32), default="cash")
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)  # bank/txn ref
    paid_at: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="CONFIRMED", index=True)  # or VOIDED
    recorded_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Bank-transfer traceability: money came FROM the customer's account TO ours.
    # from_* = payer (customer); to_* = our receiving account.
    txid: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    from_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    to_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
