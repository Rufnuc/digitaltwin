"""Phase 5: document ingestion pipeline (OCR abstraction, matching, review)."""
from __future__ import annotations

import io
import json

from app.core.enums import DocumentStatus
from app.models.provenance import Document
from app.seed.demo_data import seed
from app.services.analytics import dashboard_summary
from app.services.document_processing.base import StructuredJSONProvider
from app.services.document_processing.matcher import match_customer, match_product
from app.services.document_processing.pipeline import (
    approve_extraction,
    process_document,
    reject_extraction,
)
from app.services.document_processing.validator import validate


def _doc_bytes(customer="Customer 1", desc="Oil pump 200", qty=2, price=1000, line_total=None):
    lt = qty * price if line_total is None else line_total
    return json.dumps({
        "invoice_number": "OCR-1", "invoice_date": "2025-06-15",
        "customer_name": customer, "currency": "NGN", "tax": 0, "discount": 0,
        "lines": [{"description": desc, "quantity": qty, "unit_price": price,
                   "line_total": lt, "confidence": 0.95}],
    }).encode()


def _make_doc(db) -> Document:
    d = Document(filename="scan.json", content_type="application/json",
                 storage_key="k", status=DocumentStatus.UPLOADED.value)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def test_structured_provider_parses():
    ex = StructuredJSONProvider().extract_invoice(_doc_bytes(), "application/json")
    assert ex.invoice_number == "OCR-1"
    assert ex.customer_name == "Customer 1"
    assert len(ex.lines) == 1 and ex.lines[0].line_total == 2000


def test_matcher_matches_known_and_rejects_unknown(db):
    seed(db)
    assert match_customer(db, "Customer 1").id is not None
    assert match_product(db, "Oil pump 200").id is not None
    # Unrelated text -> below threshold -> no id (never auto-merge).
    assert match_customer(db, "Zzz Totally Unknown Corp").id is None


def test_validator_flags_bad_arithmetic():
    ex = StructuredJSONProvider().extract_invoice(_doc_bytes(line_total=2500), "application/json")
    v = validate(ex)
    assert v["arithmetic_ok"] is False
    assert any("line_total" in i for i in v["issues"])


def test_pipeline_high_confidence_is_ai_extracted(db):
    seed(db)
    doc = _make_doc(db)
    staged = process_document(db, doc, _doc_bytes())
    assert staged.status == "AI_EXTRACTED"
    assert staged.matched["customer"]["id"] is not None
    assert staged.matched["lines"][0]["product_id"] is not None
    assert doc.status == "EXTRACTED"


def test_pipeline_unknown_customer_needs_review(db):
    seed(db)
    doc = _make_doc(db)
    staged = process_document(db, doc, _doc_bytes(customer="Nobody Ltd"))
    assert staged.status == "NEEDS_REVIEW"
    assert staged.matched["customer"]["id"] is None


def test_approve_materialises_verified_invoice_into_books(db):
    seed(db)
    before = dashboard_summary(db)["data_status"]["real_invoices"]
    doc = _make_doc(db)
    staged = process_document(db, doc, _doc_bytes())

    invoice = approve_extraction(db, staged, user_id=1)
    assert invoice.verification_status == "VERIFIED"
    assert invoice.data_origin == "REAL"
    assert invoice.source_document_id == doc.id
    assert invoice.lines[0].product_id is not None
    assert invoice.total == 2000
    assert staged.status == "VERIFIED" and staged.created_invoice_id == invoice.id
    # Now counts as a real invoice in the books.
    after = dashboard_summary(db)["data_status"]["real_invoices"]
    assert after == before + 1


def test_reject_leaves_no_invoice(db):
    seed(db)
    doc = _make_doc(db)
    staged = process_document(db, doc, _doc_bytes(customer="Nobody Ltd"))
    reject_extraction(db, staged, user_id=1, notes="wrong customer")
    assert staged.status == "REJECTED"
    assert staged.created_invoice_id is None


def test_document_api_roundtrip(client, auth_headers, db):
    seed(db)
    files = {"file": ("scan.json", io.BytesIO(_doc_bytes()), "application/json")}
    up = client.post("/api/v1/documents", headers=auth_headers("STAFF"), files=files)
    assert up.status_code == 201, up.text
    ex_id = up.json()["extraction"]["id"]

    queue = client.get("/api/v1/extractions", headers=auth_headers("STAFF"))
    assert any(s["id"] == ex_id for s in queue.json()["items"])

    # Staff cannot approve into the books; manager can.
    assert client.post(f"/api/v1/extractions/{ex_id}/approve", headers=auth_headers("STAFF"),
                       json={}).status_code == 403
    ok = client.post(f"/api/v1/extractions/{ex_id}/approve", headers=auth_headers("MANAGER"),
                     json={})
    assert ok.status_code == 200, ok.text
    assert ok.json()["invoice_id"] is not None
