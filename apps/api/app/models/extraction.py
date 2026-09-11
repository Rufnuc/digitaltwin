from __future__ import annotations

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import VerificationStatus
from app.db.base import Base, TimestampMixin


class ExtractedInvoice(Base, TimestampMixin):
    """A candidate invoice extracted from a document, pending human review.

    Staging keeps unverified OCR/import output OUT of analytics until a reviewer
    approves it — at which point it is materialised into a real, VERIFIED Invoice
    (`created_invoice_id`). The original extracted values are always retained here
    even after correction (spec §11, §13, §14).
    """

    __tablename__ = "extracted_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), index=True, nullable=False
    )
    data_import_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32), default=VerificationStatus.NEEDS_REVIEW.value, index=True
    )
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    extracted: Mapped[dict] = mapped_column(JSON, default=dict)   # raw InvoiceExtraction
    matched: Mapped[dict] = mapped_column(JSON, default=dict)     # customer/product matches
    validation: Mapped[dict] = mapped_column(JSON, default=dict)  # arithmetic checks

    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
