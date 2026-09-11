"""Historical-document ingestion pipeline (spec §12).

PHYSICAL → SCAN → ARCHIVE → OCR → FIELD EXTRACTION → CUSTOMER/PRODUCT MATCH →
MATHEMATICAL VALIDATION → CONFIDENCE → HUMAN REVIEW → DATABASE.

Extraction is staged in `ExtractedInvoice` and only becomes a real, VERIFIED
Invoice on human approval — so unverified data never reaches analytics.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.enums import DataOrigin, DocumentStatus, VerificationStatus
from app.models.extraction import ExtractedInvoice
from app.models.invoice import Invoice, InvoiceLine
from app.models.provenance import Document
from app.services.document_processing.base import get_ocr_provider
from app.services.document_processing.matcher import match_customer, match_product
from app.services.document_processing.validator import validate

# Above this composite confidence (and with no issues) an extraction is tagged
# AI_EXTRACTED; otherwise it is flagged NEEDS_REVIEW.
AUTO_CONFIDENCE = 0.85


def _composite_confidence(extraction, customer_conf: float, product_confs: list[float]) -> float:
    parts = [extraction.overall_confidence or 0.0]
    if extraction.customer_name:
        parts.append(customer_conf)
    parts.extend(product_confs or [])
    return round(sum(parts) / len(parts), 3) if parts else 0.0


def process_document(db: Session, document: Document, data: bytes) -> ExtractedInvoice:
    provider = get_ocr_provider()
    extraction = provider.extract_invoice(data, document.content_type or "application/json")

    cust = match_customer(db, extraction.customer_name)
    line_matches = [match_product(db, ln.description) for ln in extraction.lines]
    validation = validate(extraction)

    confidence = _composite_confidence(
        extraction, cust.confidence, [m.confidence for m in line_matches]
    )
    all_lines_matched = all(m.id is not None for m in line_matches) if line_matches else False
    needs_review = (
        not validation["arithmetic_ok"]
        or cust.id is None
        or not all_lines_matched
        or confidence < AUTO_CONFIDENCE
    )
    status = (
        VerificationStatus.NEEDS_REVIEW.value
        if needs_review
        else VerificationStatus.AI_EXTRACTED.value
    )

    matched = {
        "customer": {
            "id": cust.id, "confidence": cust.confidence, "matched_text": cust.matched_text,
        },
        "lines": [
            {"product_id": m.id, "confidence": m.confidence, "matched_text": m.matched_text}
            for m in line_matches
        ],
    }

    document.status = DocumentStatus.EXTRACTED.value
    document.ocr_confidence = extraction.overall_confidence

    staged = ExtractedInvoice(
        document_id=document.id,
        data_import_id=document.data_import_id,
        status=status,
        overall_confidence=confidence,
        extracted=asdict(extraction),
        matched=matched,
        validation=validation,
    )
    db.add(staged)
    db.commit()
    db.refresh(staged)
    return staged


def approve_extraction(
    db: Session, staged: ExtractedInvoice, user_id: int | None, corrections: dict | None = None
) -> Invoice:
    """Materialise a staged extraction into a real, VERIFIED invoice.

    `corrections` may override customer_id and per-line product_id/values; the
    original extracted values remain stored on `staged.extracted`.
    """
    ex = staged.extracted or {}
    matched = staged.matched or {}
    corrections = corrections or {}

    customer_id = corrections.get("customer_id", (matched.get("customer") or {}).get("id"))
    line_product_ids = corrections.get(
        "line_product_ids", [ln.get("product_id") for ln in matched.get("lines", [])]
    )

    inv_date = ex.get("invoice_date")
    parsed_date = (
        datetime.strptime(inv_date[:10], "%Y-%m-%d").date() if inv_date else date.today()
    )

    lines_data = ex.get("lines", [])
    subtotal = round(sum(float(ln.get("line_total", 0) or 0) for ln in lines_data), 2)
    tax = float(ex.get("tax", 0) or 0)
    discount = float(ex.get("discount", 0) or 0)
    total = round(subtotal + tax - discount, 2)

    invoice = Invoice(
        invoice_number=ex.get("invoice_number") or f"DOC-{staged.document_id}",
        invoice_date=parsed_date,
        customer_id=customer_id,
        currency=ex.get("currency", "NGN"),
        subtotal=subtotal,
        tax=tax,
        discount=discount,
        total=total,
        data_origin=DataOrigin.REAL.value,
        verification_status=VerificationStatus.VERIFIED.value,
        confidence=staged.overall_confidence,
        extraction_method=(ex.get("provider") or "ocr"),
        source_document_id=staged.document_id,
        data_import_id=staged.data_import_id,
        verified_by_id=user_id,
        verified_at=datetime.now(timezone.utc),
    )
    for i, ln in enumerate(lines_data):
        product_id = line_product_ids[i] if i < len(line_product_ids) else None
        invoice.lines.append(
            InvoiceLine(
                product_id=product_id,
                original_description=ln.get("description"),
                quantity=float(ln.get("quantity", 0) or 0),
                unit_price=float(ln.get("unit_price", 0) or 0),
                line_total=float(ln.get("line_total", 0) or 0),
                data_origin=DataOrigin.REAL.value,
                verification_status=VerificationStatus.VERIFIED.value,
                verified_by_id=user_id,
            )
        )
    db.add(invoice)
    db.flush()

    staged.status = VerificationStatus.VERIFIED.value
    staged.created_invoice_id = invoice.id
    staged.reviewed_by_id = user_id
    db.commit()
    db.refresh(invoice)
    return invoice


def reject_extraction(
    db: Session, staged: ExtractedInvoice, user_id: int | None, notes: str | None = None
) -> ExtractedInvoice:
    staged.status = VerificationStatus.REJECTED.value
    staged.reviewed_by_id = user_id
    staged.review_notes = notes
    db.commit()
    db.refresh(staged)
    return staged
