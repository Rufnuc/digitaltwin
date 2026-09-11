from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, String
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
    total: Mapped[float] = mapped_column(MONEY, default=0)

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
