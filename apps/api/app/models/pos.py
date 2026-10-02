"""Point-of-sale (card terminal) payments and their reconciliation to invoices.

A card tap on a POS terminal is anonymous — the bank's transaction carries an
amount, terminal id, reference (RRN) and time, but no customer. We link it to an
invoice in one of two ways:

  * ExpectedPosPayment — created the moment a cashier charges an invoice ("expect
    ₦X on terminal T"), optionally pushed to the terminal so it pops the amount.
    The incoming webhook is matched against it (amount + terminal + time), which
    works for full AND partial payments.
  * Otherwise the PosTransaction lands UNMATCHED for one-tap assignment, with
    ranked suggestions of the most likely invoice.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.organization import MONEY


class ExpectedPosPayment(Base, TimestampMixin):
    """A cashier's statement that a customer is about to pay ₦amount on a POS
    terminal for an invoice. Reconciled against the terminal's webhook."""

    __tablename__ = "expected_pos_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount: Mapped[float] = mapped_column(MONEY, nullable=False)
    terminal_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    # PENDING | MATCHED | EXPIRED | CANCELLED
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Set when this expectation was pushed to the terminal (provider request id).
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pushed: Mapped[bool] = mapped_column(default=False)
    pos_transaction_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)


class PosTransaction(Base, TimestampMixin):
    """A card transaction reported by a POS provider's webhook. Stored once
    (deduped on provider + provider_txn_id) and reconciled to an invoice."""

    __tablename__ = "pos_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # The provider's own transaction id — the idempotency key for retransmits.
    provider_txn_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    terminal_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    amount: Mapped[float] = mapped_column(MONEY, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)  # RRN / narration
    masked_pan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    # UNMATCHED | MATCHED | IGNORED
    status: Mapped[str] = mapped_column(String(16), default="UNMATCHED", index=True)
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="SET NULL"), index=True, nullable=True
    )
    payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # How the match was made: AUTO_EXPECTED | AUTO_BALANCE | MANUAL (null while unmatched).
    match_method: Mapped[str | None] = mapped_column(String(24), nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
