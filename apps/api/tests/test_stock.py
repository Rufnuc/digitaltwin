"""Stock engine: lots (markers), FIFO sale allocation, transfers, traceability."""
from __future__ import annotations

from datetime import date

import pytest

from app.models.customer import Customer
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.services import stock


@pytest.fixture
def seeded(db):
    p = Product(code="BRK12", name="Brake Pad", purchase_cost=1000, selling_price=1500)
    lagos = Warehouse(code="WH-LAG", name="Lagos Main")
    abuja = Warehouse(code="WH-ABJ", name="Abuja Depot")
    cust = Customer(code="CUS-1", name="Acme Motors")
    db.add_all([p, lagos, abuja, cust])
    db.commit()
    return {"product": p.id, "lagos": lagos.id, "abuja": abuja.id, "customer": cust.id}


def test_receive_creates_marker_with_lineage(db, seeded):
    lot = stock.receive_stock(db, product_id=seeded["product"], warehouse_id=seeded["lagos"],
                              quantity=100, unit_cost=1000, received_date=date(2026, 1, 5))
    assert lot.lot_code.startswith("LOT-BRK12-20260105-")
    assert lot.quantity_remaining == 100 and lot.status == "IN_STOCK"
    detail = stock.lot_detail(db, lot.id)
    assert detail["warehouse"] == "Lagos Main"
    assert detail["movements"][0]["type"] == "RECEIPT"


def test_fifo_sale_records_buyer_and_depletes_oldest(db, seeded):
    # Two lots; the older one should be consumed first.
    old = stock.receive_stock(db, product_id=seeded["product"], warehouse_id=seeded["lagos"],
                              quantity=30, unit_cost=900, received_date=date(2026, 1, 1))
    stock.receive_stock(db, product_id=seeded["product"], warehouse_id=seeded["lagos"],
                        quantity=50, unit_cost=1100, received_date=date(2026, 2, 1))

    allocs = stock.allocate_for_sale(db, product_id=seeded["product"], warehouse_id=seeded["lagos"],
                                     quantity=40, invoice_id=None, customer_id=seeded["customer"])
    # 30 from the old lot, 10 from the new lot.
    assert [a["quantity"] for a in allocs] == [30, 10]
    assert stock.on_hand(db, seeded["product"], seeded["lagos"]) == 40

    detail = stock.lot_detail(db, old["id"] if isinstance(old, dict) else old.id)
    assert "Acme Motors" in detail["sold_to"]
    assert detail["status"] == "DEPLETED"


def test_insufficient_stock_raises(db, seeded):
    stock.receive_stock(db, product_id=seeded["product"], warehouse_id=seeded["lagos"], quantity=5)
    with pytest.raises(stock.StockError):
        stock.allocate_for_sale(db, product_id=seeded["product"], warehouse_id=seeded["lagos"],
                                quantity=10)


def test_transfer_preserves_lineage_and_moves_on_hand(db, seeded):
    stock.receive_stock(db, product_id=seeded["product"], warehouse_id=seeded["lagos"],
                        quantity=60, unit_cost=1000, received_date=date(2026, 1, 1))
    stock.transfer_stock(db, product_id=seeded["product"], from_warehouse_id=seeded["lagos"],
                         to_warehouse_id=seeded["abuja"], quantity=25)
    assert stock.on_hand(db, seeded["product"], seeded["lagos"]) == 35
    assert stock.on_hand(db, seeded["product"], seeded["abuja"]) == 25
    # The product now sits in two warehouses.
    places = {w["warehouse"] for w in stock.on_hand_by_warehouse(db, seeded["product"])}
    assert places == {"Lagos Main", "Abuja Depot"}


def test_sell_endpoint_moves_stock(client, auth_headers, db, seeded):
    stock.receive_stock(db, product_id=seeded["product"], warehouse_id=seeded["lagos"],
                        quantity=20, unit_cost=1000)
    r = client.post("/api/v1/invoices/sell", headers=auth_headers("STAFF"), json={
        "invoice_number": "INV-1001", "invoice_date": "2026-03-01",
        "warehouse_id": seeded["lagos"], "customer_id": seeded["customer"],
        "lines": [{"product_id": seeded["product"], "quantity": 8, "unit_price": 1500}],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["invoice"]["total"] == 12000
    assert body["allocations"][0]["lots"][0]["quantity"] == 8
    assert stock.on_hand(db, seeded["product"], seeded["lagos"]) == 12


def test_sold_line_exposes_product_name_without_description(client, auth_headers, db, seeded):
    # A sale carries no free-text description, so the invoice must surface the linked
    # product's name — otherwise the printed invoice just reads "Product".
    stock.receive_stock(db, product_id=seeded["product"], warehouse_id=seeded["lagos"],
                        quantity=20, unit_cost=1000)
    r = client.post("/api/v1/invoices/sell", headers=auth_headers("STAFF"), json={
        "invoice_number": "INV-1003", "invoice_date": "2026-03-01",
        "warehouse_id": seeded["lagos"], "customer_id": seeded["customer"],
        "lines": [{"product_id": seeded["product"], "quantity": 5, "unit_price": 1500}],
    })
    assert r.status_code == 201, r.text
    invoice_id = r.json()["invoice"]["id"]

    detail = client.get(f"/api/v1/invoices/{invoice_id}", headers=auth_headers("STAFF")).json()
    line = detail["lines"][0]
    assert line["original_description"] is None
    assert line["product_name"] == "Brake Pad"


def test_sell_endpoint_rejects_oversell(client, auth_headers, db, seeded):
    stock.receive_stock(db, product_id=seeded["product"], warehouse_id=seeded["lagos"], quantity=3)
    r = client.post("/api/v1/invoices/sell", headers=auth_headers("STAFF"), json={
        "invoice_number": "INV-1002", "invoice_date": "2026-03-01",
        "warehouse_id": seeded["lagos"],
        "lines": [{"product_id": seeded["product"], "quantity": 10, "unit_price": 1500}],
    })
    assert r.status_code == 422
    # Nothing was drawn — the invoice was rolled back.
    assert stock.on_hand(db, seeded["product"], seeded["lagos"]) == 3
