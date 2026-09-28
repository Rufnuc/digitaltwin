"""Shipping documents attached to a purchase, and multi-currency supplier payments."""
from __future__ import annotations

import pytest

from app.models.product import Product
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.services import payables, procurement


@pytest.fixture
def purchase(db):
    p = Product(code="DOC-P", name="Belt", purchase_cost=100, selling_price=200)
    s = Supplier(code="DOC-S", name="Sup Co", currency="NGN")
    wh = Warehouse(code="DOC-W", name="WH")
    db.add_all([p, s, wh])
    db.commit()
    pur = procurement.create_request(
        db, supplier_id=s.id,
        lines=[{"product_id": p.id, "quantity": 10, "unit_cost": 100}],
    )
    return {"id": pur["id"], "supplier": s.id}


def test_document_lifecycle(db, purchase):
    pid = purchase["id"]
    assert procurement.list_documents(db, pid) == []

    d = procurement.add_document(
        db, purchase_id=pid, filename="waybill.pdf", data=b"%PDF-1.4 fake",
        content_type="application/pdf", kind="shipping", note="park receipt",
    )
    assert d and d["filename"] == "waybill.pdf" and d["size_bytes"] == len(b"%PDF-1.4 fake")

    docs = procurement.list_documents(db, pid)
    assert len(docs) == 1 and docs[0]["kind"] == "shipping"

    # Count surfaces on the purchase dict.
    assert procurement.get_purchase(db, pid)["document_count"] == 1

    # Fetch the stored file back through the driver.
    got = procurement.get_document(db, pid, d["id"])
    assert got is not None
    from app.services.storage import get_storage
    with open(get_storage().path_for(got.storage_key), "rb") as fh:
        assert fh.read() == b"%PDF-1.4 fake"

    # Wrong purchase id must not resolve someone else's document.
    assert procurement.get_document(db, pid + 999, d["id"]) is None

    assert procurement.delete_document(db, pid, d["id"]) is True
    assert procurement.list_documents(db, pid) == []
    assert procurement.delete_document(db, pid, d["id"]) is False


def test_add_document_missing_purchase(db):
    assert procurement.add_document(db, purchase_id=123456, filename="x",
                                    data=b"x") is None


def test_same_currency_payment_nets_balance(db, purchase):
    r = payables.record_supplier_payment(db, purchase_id=purchase["id"], amount=400,
                                         currency="NGN", method="transfer")
    assert r["status"] == "OK"
    assert r["amount_paid"] == 400.0 and r["balance"] == 600.0


def test_foreign_currency_payment_recorded_but_not_netted(db, purchase):
    """Paying an NGN-priced order in USD is logged for the trail but does not
    move the naira balance (FX rates vary and aren't tracked here)."""
    r = payables.record_supplier_payment(db, purchase_id=purchase["id"], amount=5,
                                         currency="USD", method="transfer")
    assert r["status"] == "OK"
    # Balance unchanged: the USD payment isn't summed into the NGN amount_paid.
    assert r["amount_paid"] == 0.0 and r["balance"] == 1000.0
    pays = payables.list_supplier_payments(db, purchase["id"])
    assert len(pays) == 1 and pays[0]["currency"] == "USD" and pays[0]["amount"] == 5.0
