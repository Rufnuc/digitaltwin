"""Supplier cockpit: statement (owe/paid) + slow-movers over the supply chain."""
from __future__ import annotations

import pytest

from app.models.product import Product
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.services import payables, procurement, stock, supplier_trace


@pytest.fixture
def chain(db):
    p = Product(code="SM-P", name="Slow Belt", purchase_cost=100, selling_price=200)
    s = Supplier(code="SM-S", name="Sup Co")
    wh = Warehouse(code="SM-W", name="WH")
    db.add_all([p, s, wh])
    db.commit()
    # Received 10 from the supplier, sold 2.
    pur = procurement.create_request(db, supplier_id=s.id,
                                     lines=[{"product_id": p.id, "quantity": 10, "unit_cost": 100}])
    procurement.receive(db, purchase_id=pur["id"], warehouse_id=wh.id, transport_cost=0)
    stock.allocate_for_sale(db, product_id=p.id, warehouse_id=wh.id, quantity=2, commit=True)
    return {"product": p.id, "supplier": s.id, "purchase": pur["id"]}


def test_statement_and_slow_movers(db, chain):
    d = supplier_trace.supplier_detail(db, chain["supplier"])
    assert d["status"] == "OK"
    # Statement lists the purchase with its balance (total 1000, unpaid).
    assert len(d["statement"]) == 1
    st = d["statement"][0]
    assert st["total"] == 1000.0 and st["balance"] == 1000.0
    assert d["we_owe"] == 1000.0 and d["total_paid"] == 0.0
    # Slow-movers: received 10, sold 2, still holding 8.
    sm = next(m for m in d["slow_movers"] if m["product_id"] == chain["product"])
    assert sm["received"] == 10 and sm["sold"] == 2 and sm["on_hand"] == 8


def test_recording_supplier_payment_moves_owe_and_paid(db, chain):
    payables.record_supplier_payment(db, purchase_id=chain["purchase"], amount=400,
                                     method="transfer", reference="TRX-1")
    d = supplier_trace.supplier_detail(db, chain["supplier"])
    assert d["total_paid"] == 400.0 and d["we_owe"] == 600.0
    assert d["statement"][0]["amount_paid"] == 400.0 and d["statement"][0]["balance"] == 600.0
    assert d["payments"][0]["method"] == "transfer" and d["payments"][0]["reference"] == "TRX-1"
