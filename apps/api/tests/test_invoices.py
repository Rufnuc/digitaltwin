"""Invoice creation + arithmetic validation tests (spec §13)."""
from __future__ import annotations


def test_invoice_arithmetic_balances_and_verifies(client, auth_headers):
    payload = {
        "invoice_number": "INV-TEST-1",
        "invoice_date": "2025-01-15",
        "currency": "USD",
        "tax": 5.0,
        "discount": 0.0,
        "lines": [
            {"quantity": 2, "unit_price": 10.0, "line_total": 20.0, "unit_cost": 6.0},
            {"quantity": 1, "unit_price": 30.0, "line_total": 30.0, "unit_cost": 18.0},
        ],
    }
    r = client.post("/api/v1/invoices", headers=auth_headers("STAFF"), json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["subtotal"] == 50.0
    assert body["total"] == 55.0
    assert body["verification_status"] == "VERIFIED"


def test_invoice_bad_arithmetic_flagged_for_review_not_corrected(client, auth_headers):
    payload = {
        "invoice_number": "INV-TEST-2",
        "invoice_date": "2025-01-16",
        "lines": [
            # 2 * 10 = 20, but line_total claims 25 -> must be flagged, not silently fixed
            {"quantity": 2, "unit_price": 10.0, "line_total": 25.0},
        ],
    }
    r = client.post("/api/v1/invoices", headers=auth_headers("STAFF"), json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["verification_status"] == "NEEDS_REVIEW"
    # original (claimed) line_total preserved, not overwritten
    assert body["lines"][0]["line_total"] == 25.0
