"""Procurement: supplier request → order → receive into stock with transport cost."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.supplier import Supplier
from app.models.warehouse import StockLot, Warehouse
from app.services import stock


@pytest.fixture
def setup(db):
    p = Product(code="RQ-P", name="Belt", purchase_cost=100, selling_price=180)
    s = Supplier(code="RQ-S", name="Shandong")
    wh = Warehouse(code="RQ-W", name="Lagos")
    db.add_all([p, s, wh])
    db.commit()
    return {"product": p.id, "supplier": s.id, "warehouse": wh.id}


def test_create_request_computes_totals(client, auth_headers, setup):
    r = client.post("/api/v1/purchases", headers=auth_headers("STAFF"), json={
        "supplier_id": setup["supplier"], "lines": [
            {"product_id": setup["product"], "quantity": 10, "unit_cost": 100},
            {"product_id": setup["product"], "quantity": 5, "unit_cost": 200},
        ],
    })
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "REQUEST" and b["reference"].startswith("PR-")
    assert b["subtotal"] == 2000.0 and b["line_count"] == 2
    assert b["supplier_name"] == "Shandong"


def test_status_transition_and_receive_blocks_via_status_endpoint(client, auth_headers, setup):
    pid = client.post("/api/v1/purchases", headers=auth_headers("STAFF"), json={
        "supplier_id": setup["supplier"],
        "lines": [{"product_id": setup["product"], "quantity": 10, "unit_cost": 100}],
    }).json()["id"]
    r = client.patch(f"/api/v1/purchases/{pid}/status", headers=auth_headers("MANAGER"),
                     json={"status": "ORDERED"})
    assert r.status_code == 200 and r.json()["status"] == "ORDERED"
    # RECEIVED must go through the receive action, not the status endpoint.
    bad = client.patch(f"/api/v1/purchases/{pid}/status", headers=auth_headers("MANAGER"),
                       json={"status": "RECEIVED"})
    assert bad.status_code == 400, bad.text


def test_receive_creates_stock_with_freight_in_landed_cost(client, auth_headers, db, setup):
    pid = client.post("/api/v1/purchases", headers=auth_headers("STAFF"), json={
        "supplier_id": setup["supplier"],
        "lines": [{"product_id": setup["product"], "quantity": 10, "unit_cost": 100}],
    }).json()["id"]
    r = client.post(f"/api/v1/purchases/{pid}/receive", headers=auth_headers("MANAGER"),
                    json={"warehouse_id": setup["warehouse"], "transport_cost": 200})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "RECEIVED" and b["transport_cost"] == 200.0
    assert b["total"] == 1200.0  # 1000 goods + 200 freight
    # Stock came in, linked to the supplier, with freight rolled into unit cost.
    assert stock.on_hand(db, setup["product"], setup["warehouse"]) == 10
    lot = db.scalar(select(StockLot).where(StockLot.product_id == setup["product"]))
    assert lot.supplier_id == setup["supplier"]
    assert float(lot.unit_cost) == 120.0  # 100 + 200/10


def test_cannot_receive_twice(client, auth_headers, setup):
    pid = client.post("/api/v1/purchases", headers=auth_headers("STAFF"), json={
        "supplier_id": setup["supplier"],
        "lines": [{"product_id": setup["product"], "quantity": 3, "unit_cost": 100}],
    }).json()["id"]
    ok = client.post(f"/api/v1/purchases/{pid}/receive", headers=auth_headers("MANAGER"),
                     json={"warehouse_id": setup["warehouse"]})
    assert ok.status_code == 200
    again = client.post(f"/api/v1/purchases/{pid}/receive", headers=auth_headers("MANAGER"),
                        json={"warehouse_id": setup["warehouse"]})
    assert again.status_code == 400, again.text


def test_receive_requires_manager(client, auth_headers, setup):
    pid = client.post("/api/v1/purchases", headers=auth_headers("STAFF"), json={
        "supplier_id": setup["supplier"],
        "lines": [{"product_id": setup["product"], "quantity": 3, "unit_cost": 100}],
    }).json()["id"]
    r = client.post(f"/api/v1/purchases/{pid}/receive", headers=auth_headers("STAFF"),
                    json={"warehouse_id": setup["warehouse"]})
    assert r.status_code == 403, r.text
