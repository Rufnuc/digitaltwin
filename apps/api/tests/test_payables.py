"""Accounts payable (supplier side) and cash-flow summary."""
from __future__ import annotations

from datetime import date, timedelta

from app.models.expense import Expense
from app.models.invoice import Invoice
from app.models.purchase import Purchase
from app.models.supplier import Supplier
from app.services import cashflow, payables
from app.services import receivables as rc


def _purchase(db, supplier_id=None, total=1000.0, days_ago=0):
    p = Purchase(reference=f"PO-{total}-{days_ago}",
                 purchase_date=date.today() - timedelta(days=days_ago),
                 supplier_id=supplier_id, currency="NGN", subtotal=total, total=total,
                 data_origin="REAL")
    db.add(p)
    db.commit()
    return p


def test_supplier_payment_and_balance(db):
    sup = Supplier(code="SUP-X", name="Parts Import Co")
    db.add(sup)
    db.commit()
    po = _purchase(db, supplier_id=sup.id, total=5000.0, days_ago=40)

    r = payables.record_supplier_payment(db, purchase_id=po.id, amount=2000, method="transfer")
    assert r["status"] == "OK" and r["balance"] == 3000.0 and r["payment_status"] == "PARTIAL"

    over = payables.record_supplier_payment(db, purchase_id=po.id, amount=9999)
    assert over["status"] == "ERROR"

    s = payables.payables_summary(db)
    assert s["total_payable"] == 3000.0
    assert s["aging"]["31-60"] == 3000.0
    assert s["creditors"][0]["supplier_name"] == "Parts Import Co"


def test_cash_flow_summary(db):
    cust_inv = Invoice(invoice_number="CF-1", invoice_date=date.today(),
                       currency="NGN", subtotal=1000, total=1000, data_origin="REAL")
    db.add(cust_inv)
    db.add(Expense(expense_date=date.today(), category="rent", amount=300, currency="NGN",
                   data_origin="REAL"))
    db.commit()
    rc.record_payment(db, invoice_id=cust_inv.id, amount=400)  # money in
    po = _purchase(db, total=250.0)
    payables.record_supplier_payment(db, purchase_id=po.id, amount=250)  # money out

    cf = cashflow.cash_flow_summary(db, days=30)
    assert cf["money_in"] == 400.0
    assert cf["money_out"] == 250.0 + 300.0            # supplier payment + expense
    assert cf["net_cash_flow"] == 400.0 - 550.0
    assert cf["owed_to_us"] == 600.0                   # 1000 invoice - 400 paid
    assert cf["we_owe"] == 0.0                          # the only purchase is fully paid


def test_payables_and_cashflow_api(client, auth_headers, db):
    sup = Supplier(code="SUP-Y", name="Api Supplier")
    db.add(sup)
    db.commit()
    po = _purchase(db, supplier_id=sup.id, total=1000.0)

    h = auth_headers("MANAGER")
    pay = client.post(f"/api/v1/payables/purchases/{po.id}/payments", headers=h,
                      json={"amount": 400, "method": "transfer"})
    assert pay.status_code == 200 and pay.json()["balance"] == 600.0

    summ = client.get("/api/v1/payables/summary", headers=h)
    assert summ.status_code == 200 and summ.json()["total_payable"] >= 600.0

    cf = client.get("/api/v1/cashflow/summary", headers=h)
    assert cf.status_code == 200 and "net_position" in cf.json()

    db.expire_all()
    from app.services.ai.tools import execute_tool
    assert execute_tool(db, "get_payables", {})["total_payable"] >= 600.0
    assert "net_position" in execute_tool(db, "get_cash_flow", {})
