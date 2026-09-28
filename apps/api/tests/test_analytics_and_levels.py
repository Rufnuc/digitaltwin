"""Stock levels, warehouse summary, and per-customer / per-product analytics."""
from __future__ import annotations

from datetime import date

import pytest

from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceLine
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.services import (
    customer_analytics,
    procurement,
    product_analytics,
    stock,
)


@pytest.fixture
def seeded(db):
    p = Product(code="AN-P", name="Analytics Belt", purchase_cost=100, selling_price=250,
                category="Belts", reorder_level=5)
    s = Supplier(code="AN-S", name="Sup", currency="NGN")
    wh = Warehouse(code="AN-W", name="Main WH")
    db.add_all([p, s, wh])
    db.commit()
    # Receive 10, sell 2.
    pur = procurement.create_request(db, supplier_id=s.id,
                                     lines=[{"product_id": p.id, "quantity": 10, "unit_cost": 100}])
    procurement.receive(db, purchase_id=pur["id"], warehouse_id=wh.id, transport_cost=0)
    stock.allocate_for_sale(db, product_id=p.id, warehouse_id=wh.id, quantity=2, commit=True)
    return {"product": p.id, "supplier": s.id, "warehouse": wh.id}


def test_levels_search_and_low_stock(db, seeded):
    r = stock.levels(db, q="Analytics")
    row = next(x for x in r["items"] if x["product_id"] == seeded["product"])
    assert row["on_hand"] == 8 and row["value"] == 800.0
    assert "Belts" in r["categories"]
    # 8 on hand > reorder 5 -> not low
    assert row["low"] is False
    # Filter to only low stock excludes it.
    low = stock.levels(db, low_stock=True)
    assert all(x["product_id"] != seeded["product"] for x in low["items"])


def test_levels_warehouse_filter(db, seeded):
    r = stock.levels(db, warehouse_id=seeded["warehouse"])
    assert any(x["product_id"] == seeded["product"] and x["on_hand"] == 8 for x in r["items"])


def test_warehouse_summary(db, seeded):
    r = stock.warehouse_summary(db, seeded["warehouse"])
    assert r is not None
    assert r["total_units"] == 8 and r["product_count"] == 1
    assert r["total_value"] == 800.0
    assert any(m["type"] == "RECEIPT" for m in r["recent_movements"])
    assert stock.warehouse_summary(db, 999999) is None


def test_customer_analytics(db):
    c = Customer(code="AN-C", name="Repeat Buyer")
    db.add(c)
    db.commit()
    for i, d in enumerate([date(2026, 1, 5), date(2026, 3, 5)]):
        db.add(Invoice(invoice_number=f"AN-INV-{i}", invoice_date=d,
                       customer_id=c.id, total=1000 * (i + 1)))
    db.commit()
    r = customer_analytics.customer_analytics(db, c.id)
    assert r["orders"] == 2 and r["revenue"] == 3000.0
    assert r["returning"] is True and r["avg_order_value"] == 1500.0
    assert len(r["monthly"]) == 12
    assert customer_analytics.customer_analytics(db, 999999) is None


def test_product_analytics(db, seeded):
    r = product_analytics.product_analytics(db, seeded["product"])
    assert r["total_received"] == 10 and r["total_sold"] == 2 and r["on_hand"] == 8
    assert len(r["monthly"]) == 12
    # The received-10 shows up in the current month bucket.
    assert sum(m["received"] for m in r["monthly"]) == 10
    assert sum(m["sold"] for m in r["monthly"]) == 2
    assert product_analytics.product_analytics(db, 999999) is None
