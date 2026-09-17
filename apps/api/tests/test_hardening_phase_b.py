"""Phase B hardening: one stock source of truth + invoice-edit protection."""
from __future__ import annotations

import pytest

from app.models.customer import Customer
from app.models.inventory import Inventory
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


# --- B1: single stock source of truth --------------------------------------
def test_stock_value_is_lot_authoritative_and_ignores_legacy(db, shop):
    stock.receive_stock(db, product_id=shop["product"], warehouse_id=shop["wh"],
                        quantity=10, unit_cost=1000)
    # A stale legacy Inventory row for the same product must be ignored (lots win).
    db.add(Inventory(product_id=shop["product"], quantity_on_hand=999, unit_cost=1000))
    db.commit()
    assert stock.stock_value(db) == 10000.0


def test_stock_value_reflects_a_sale(client, auth_headers, db, shop):
    stock.receive_stock(db, product_id=shop["product"], warehouse_id=shop["wh"],
                        quantity=10, unit_cost=1000)
    assert stock.stock_value(db) == 10000.0
    r = client.post("/api/v1/invoices/sell", headers=auth_headers("STAFF"), json={
        "invoice_number": "SV-1", "invoice_date": "2026-01-01", "warehouse_id": shop["wh"],
        "lines": [{"product_id": shop["product"], "quantity": 4, "unit_price": 1500}],
    })
    assert r.status_code == 201, r.text
    assert stock.stock_value(db) == 6000.0  # value dropped by the 4 units sold


def test_inventory_direct_write_refused(client, auth_headers, db, shop):
    db.add(Inventory(product_id=shop["product"], quantity_on_hand=5, unit_cost=1000))
    db.commit()
    # PATCH / POST / DELETE on inventory are not exposed (read-only resource).
    r = client.patch("/api/v1/inventory/1", headers=auth_headers("MANAGER"),
                      json={"quantity_on_hand": 500})
    assert r.status_code in (404, 405), r.text
    r2 = client.post("/api/v1/inventory", headers=auth_headers("MANAGER"),
                     json={"product_id": shop["product"], "quantity_on_hand": 1})
    assert r2.status_code in (404, 405), r2.text


# --- B2: invoice-edit protection -------------------------------------------
def test_edit_paid_invoice_amounts_blocked(client, auth_headers):
    inv = client.post("/api/v1/invoices", headers=auth_headers("STAFF"), json={
        "invoice_number": "EP-1", "invoice_date": "2026-01-01",
        "lines": [{"quantity": 1, "unit_price": 1000.0, "line_total": 1000.0}],
    }).json()
    pay = client.post(f"/api/v1/receivables/invoices/{inv['id']}/payments",
                      headers=auth_headers("STAFF"), json={"amount": 500, "method": "cash"})
    assert pay.status_code == 200, pay.text
    edit = client.patch(f"/api/v1/invoices/{inv['id']}", headers=auth_headers("MANAGER"),
                        json={"tax": 50})
    assert edit.status_code == 409, edit.text


def test_edit_fulfilled_invoice_lines_blocked(client, auth_headers, db, shop):
    stock.receive_stock(db, product_id=shop["product"], warehouse_id=shop["wh"], quantity=20)
    sold = client.post("/api/v1/invoices/sell", headers=auth_headers("STAFF"), json={
        "invoice_number": "EF-1", "invoice_date": "2026-01-01", "warehouse_id": shop["wh"],
        "lines": [{"product_id": shop["product"], "quantity": 5, "unit_price": 1500}],
    }).json()
    inv_id = sold["invoice"]["id"]
    edit = client.patch(f"/api/v1/invoices/{inv_id}", headers=auth_headers("MANAGER"),
                        json={"lines": [{"product_id": shop["product"], "quantity": 1,
                                         "unit_price": 1500}]})
    assert edit.status_code == 409, edit.text


def test_edit_unpaid_invoice_still_allowed_and_status_consistent(client, auth_headers):
    inv = client.post("/api/v1/invoices", headers=auth_headers("STAFF"), json={
        "invoice_number": "EU-1", "invoice_date": "2026-01-01",
        "lines": [{"quantity": 1, "unit_price": 1000.0, "line_total": 1000.0}],
    }).json()
    edit = client.patch(f"/api/v1/invoices/{inv['id']}", headers=auth_headers("MANAGER"),
                        json={"tax": 100})
    assert edit.status_code == 200, edit.text
    body = edit.json()
    assert body["total"] == 1100.0
    assert body["payment_status"] == "UNPAID"
    assert body["balance"] == 1100.0


# --- B3: one safe selling path ---------------------------------------------
def test_plain_create_with_product_line_blocked(client, auth_headers, shop):
    r = client.post("/api/v1/invoices", headers=auth_headers("STAFF"), json={
        "invoice_number": "PC-1", "invoice_date": "2026-01-01",
        "lines": [{"product_id": shop["product"], "quantity": 1, "unit_price": 1500.0,
                   "line_total": 1500.0}],
    })
    assert r.status_code == 400, r.text
