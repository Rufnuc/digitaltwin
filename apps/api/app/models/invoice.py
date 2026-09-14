from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, ProvenanceMixin, TimestampMixin
from app.models.organization import MONEY


class Invoice(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), index=True, nullable=True
    )
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="NGN")

    subtotal: Mapped[float] = mapped_column(MONEY, default=0)
    discount: Mapped[float] = mapped_column(MONEY, default=0)
    tax: Mapped[float] = mapped_column(MONEY, default=0)
    shipping: Mapped[float] = mapped_column(MONEY, default=0)
    shipping_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total: Mapped[float] = mapped_column(MONEY, default=0)

    # Proof of record: who raised it, who last changed it, and the version count.
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)

    # Provenance links: where this invoice came from (paper scan / import batch).
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    data_import_id: Mapped[int | None] = mapped_column(
        ForeignKey("data_imports.id"), nullable=True
    )

    lines: Mapped[list[InvoiceLine]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLine(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id"), index=True, nullable=False
    )
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    # The verbatim text as it appeared on the source (handwriting varies); the
    # normalised match lives in product_id and may be low-confidence.
    original_description: Mapped[str | None] = mapped_column(String(512), nullable=True)

    quantity: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    unit_price: Mapped[float] = mapped_column(MONEY, default=0)
    line_total: Mapped[float] = mapped_column(MONEY, default=0)
    unit_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)  # COGS basis

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class InvoiceVersion(Base):
    """An immutable snapshot of an invoice at one point in time. A row is written on
    creation and on every edit, so the full history is preserved and auditable —
    who changed it, when, and the complete state (header + lines) at that version."""

    __tablename__ = "invoice_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id"), index=True, nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    change_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
