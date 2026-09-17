"""Phase A hardening: invoice uniqueness, idempotency, oversell prevention.

Note on concurrency: the test DB is SQLite, which serializes writers and ignores
`FOR UPDATE`, so these tests prove the *guard logic* (uniqueness, idempotent
replay, availability re-check). True parallel-writer oversell/overpay races are
covered by the row-locking added in stock.py / receivables.py but can only be
exercised against Postgres.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.customer import Customer
from app.models.payment import Payment
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.services import stock


@pytest.fixture
def shop(db):
    p = Product(code="PMP1", name="Oil Pump", purchase_cost=1000, selling_price=1500)
    wh = Warehouse(code="WH-1", name="Main")
    cust = Customer(code="C-1", name="Buyer Ltd")
    db.add_all([p, wh, cust])
    db.commit()
    return {"product": p.id, "wh": wh.id, "customer": cust.id}


# --- A1: invoice number uniqueness -----------------------------------------
def test_duplicate_invoice_number_rejected(client, auth_headers):
    payload = {
        "invoice_number": "DUP-1", "invoice_date": "2026-01-01",
        "lines": [{"quantity": 1, "unit_price": 100.0, "line_total": 100.0}],
    }
    r1 = client.post("/api/v1/invoices", headers=auth_headers("STAFF"), json=payload)
    assert r1.status_code == 201, r1.text
    r2 = client.post("/api/v1/invoices", headers=auth_headers("STAFF"), json=payload)
    assert r2.status_code == 409, r2.text


def test_sell_duplicate_number_rejected_stock_drawn_once(client, auth_headers, db, shop):
    stock.receive_stock(db, product_id=shop["product"], warehouse_id=shop["wh"], quantity=20)
    body = {
        "invoice_number": "SELL-DUP", "invoice_date": "2026-01-01",
        "warehouse_id": shop["wh"],
        "lines": [{"product_id": shop["product"], "quantity": 5, "unit_price": 1500}],
    }
    r1 = client.post("/api/v1/invoices/sell", headers=auth_headers("STAFF"), json=body)
    assert r1.status_code == 201, r1.text
    # Different key (or none) but same number → rejected by the unique constraint.
    r2 = client.post("/api/v1/invoices/sell", headers=auth_headers("STAFF"), json=body)
    assert r2.status_code == 409, r2.text
    assert stock.on_hand(db, shop["product"], shop["wh"]) == 15  # drawn once only


# --- A2: idempotency --------------------------------------------------------
def test_sell_idempotent_replay_draws_stock_once(client, auth_headers, db, shop):
    stock.receive_stock(db, product_id=shop["product"], warehouse_id=shop["wh"], quantity=20)
    body = {
        "invoice_number": "SELL-IDEM", "invoice_date": "2026-01-01",
        "warehouse_id": shop["wh"],
        "lines": [{"product_id": shop["product"], "quantity": 6, "unit_price": 1500}],
    }
    hdr = {**auth_headers("STAFF"), "Idempotency-Key": "abc-123"}
    r1 = client.post("/api/v1/invoices/sell", headers=hdr, json=body)
    r2 = client.post("/api/v1/invoices/sell", headers=hdr, json=body)
    assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
    assert r1.json()["invoice"]["id"] == r2.json()["invoice"]["id"]  # same original
    assert stock.on_hand(db, shop["product"], shop["wh"]) == 14  # 6 drawn once, not 12


def test_create_invoice_idempotent_replay(client, auth_headers, db):
    payload = {
        "invoice_number": "CR-IDEM", "invoice_date": "2026-01-01",
        "lines": [{"quantity": 2, "unit_price": 50.0, "line_total": 100.0}],
    }
    hdr = {**auth_headers("STAFF"), "Idempotency-Key": "cr-1"}
    r1 = client.post("/api/v1/invoices", headers=hdr, json=payload)
    r2 = client.post("/api/v1/invoices", headers=hdr, json=payload)
    assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
    assert r1.json()["id"] == r2.json()["id"]
    from app.models.invoice import Invoice
    assert db.scalar(select(func.count()).select_from(Invoice)
                     .where(Invoice.invoice_number == "CR-IDEM")) == 1


def test_payment_idempotent_replay_records_once(client, auth_headers, db):
    inv = client.post("/api/v1/invoices", headers=auth_headers("STAFF"), json={
        "invoice_number": "PAY-IDEM", "invoice_date": "2026-01-01",
        "lines": [{"quantity": 1, "unit_price": 1000.0, "line_total": 1000.0}],
    }).json()
    hdr = {**auth_headers("STAFF"), "Idempotency-Key": "pay-1"}
    r1 = client.post(f"/api/v1/receivables/invoices/{inv['id']}/payments", headers=hdr,
                     json={"amount": 400, "method": "cash"})
    r2 = client.post(f"/api/v1/receivables/invoices/{inv['id']}/payments", headers=hdr,
                     json={"amount": 400, "method": "cash"})
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    assert r1.json()["payment_id"] == r2.json()["payment_id"]  # replay, not a new one
    n = db.scalar(select(func.count()).select_from(Payment)
                  .where(Payment.invoice_id == inv["id"], Payment.status == "CONFIRMED"))
    assert n == 1
    assert r2.json()["balance"] == 600.0


# --- A3 / A4: oversell & overpayment guards --------------------------------
def test_sequential_draws_never_exceed_stock(client, auth_headers, db, shop):
    stock.receive_stock(db, product_id=shop["product"], warehouse_id=shop["wh"], quantity=3)
    ok = client.post("/api/v1/invoices/sell", headers=auth_headers("STAFF"), json={
        "invoice_number": "OS-1", "invoice_date": "2026-01-01", "warehouse_id": shop["wh"],
        "lines": [{"product_id": shop["product"], "quantity": 2, "unit_price": 1500}],
    })
    assert ok.status_code == 201, ok.text
    over = client.post("/api/v1/invoices/sell", headers=auth_headers("STAFF"), json={
        "invoice_number": "OS-2", "invoice_date": "2026-01-01", "warehouse_id": shop["wh"],
        "lines": [{"product_id": shop["product"], "quantity": 2, "unit_price": 1500}],
    })
    assert over.status_code == 422, over.text  # only 1 left
    assert stock.on_hand(db, shop["product"], shop["wh"]) == 1


def test_overpayment_rejected(client, auth_headers):
    inv = client.post("/api/v1/invoices", headers=auth_headers("STAFF"), json={
        "invoice_number": "OP-1", "invoice_date": "2026-01-01",
        "lines": [{"quantity": 1, "unit_price": 500.0, "line_total": 500.0}],
    }).json()
    r = client.post(f"/api/v1/receivables/invoices/{inv['id']}/payments",
                    headers=auth_headers("STAFF"), json={"amount": 600, "method": "cash"})
    assert r.status_code == 400, r.text
