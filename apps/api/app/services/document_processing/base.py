"""OCR / Document-AI provider abstraction (spec §12).

We never build OCR/handwriting recognition ourselves — commercial Document-AI
providers (Google Document AI, AWS Textract, Azure Document Intelligence) plug in
behind this seam. The default `structured_json` provider ingests machine-readable
invoice documents so the full extraction → match → validate → review pipeline
runs and is testable with zero external services; real OCR providers are selected
via OCR_PROVIDER once credentials are configured.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import settings


@dataclass
class LineExtraction:
    description: str
    quantity: float
    unit_price: float
    line_total: float
    confidence: float = 1.0


@dataclass
class InvoiceExtraction:
    """Provider-agnostic structured result of reading one invoice document."""

    invoice_number: str | None = None
    invoice_date: str | None = None  # ISO date string
    customer_name: str | None = None
    currency: str = "NGN"
    lines: list[LineExtraction] = field(default_factory=list)
    subtotal: float | None = None
    tax: float = 0.0
    discount: float = 0.0
    total: float | None = None
    overall_confidence: float = 0.0
    raw_text: str = ""
    provider: str = "none"


class OCRProvider(Protocol):
    name: str

    def extract_invoice(self, data: bytes, content_type: str) -> InvoiceExtraction: ...


class NullOCRProvider:
    name = "none"

    def extract_invoice(self, data: bytes, content_type: str) -> InvoiceExtraction:
        raise NotImplementedError(
            "No OCR provider configured. Set OCR_PROVIDER (structured_json for "
            "machine-readable docs, or a commercial Document-AI provider)."
        )


class StructuredJSONProvider:
    """Ingests a machine-readable JSON invoice (already-digitised records).

    This is NOT OCR — it is the ingestion path for documents that are already
    structured, and the deterministic test/demo backbone for the pipeline. Real
    scans go through a commercial OCR provider behind the same interface.

    Expected JSON shape (all confidences optional, default 1.0):
        {"invoice_number": "...", "invoice_date": "YYYY-MM-DD",
         "customer_name": "...", "currency": "NGN", "tax": 0, "discount": 0,
         "lines": [{"description": "...", "quantity": 2, "unit_price": 10,
                    "line_total": 20, "confidence": 0.9}]}
    """

    name = "structured_json"

    def extract_invoice(self, data: bytes, content_type: str) -> InvoiceExtraction:
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f"structured_json provider expects a JSON document: {e}") from None

        lines = [
            LineExtraction(
                description=str(row.get("description", "")).strip(),
                quantity=float(row.get("quantity", 0) or 0),
                unit_price=float(row.get("unit_price", 0) or 0),
                line_total=float(
                    row.get(
                        "line_total",
                        float(row.get("quantity", 0) or 0) * float(row.get("unit_price", 0) or 0),
                    )
                ),
                confidence=float(row.get("confidence", 1.0)),
            )
            for row in doc.get("lines", [])
        ]
        line_conf = [ln.confidence for ln in lines] or [1.0]
        overall = min(line_conf) if lines else 0.0

        return InvoiceExtraction(
            invoice_number=doc.get("invoice_number"),
            invoice_date=doc.get("invoice_date"),
            customer_name=doc.get("customer_name"),
            currency=doc.get("currency", "NGN"),
            lines=lines,
            subtotal=doc.get("subtotal"),
            tax=float(doc.get("tax", 0) or 0),
            discount=float(doc.get("discount", 0) or 0),
            total=doc.get("total"),
            overall_confidence=round(overall, 3),
            raw_text=json.dumps(doc)[:2000],
            provider=self.name,
        )


def get_ocr_provider() -> OCRProvider:
    provider = (settings.OCR_PROVIDER or "structured_json").lower()
    if provider in ("structured_json", "none_structured"):
        return StructuredJSONProvider()
    # Real Document-AI providers are wired here once credentials exist.
    # e.g. google_document_ai / aws_textract / azure -> their adapters.
    return NullOCRProvider()
