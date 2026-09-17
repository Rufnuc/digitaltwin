"""Accounts receivable — recording payments and reporting who owes what."""
from __future__ import annotations

from datetime import date, timedelta

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.services import receivables as rc


def _invoice(db, customer_id=None, total=1000.0, days_ago=0, due_days=None):
    d = date.today() - timedelta(days=days_ago)
    inv = Invoice(invoice_number=f"INV-{total}-{days_ago}", invoice_date=d,
                  customer_id=customer_id, currency="NGN", subtotal=total, total=total,
                  due_date=(d + timedelta(days=due_days)) if due_days is not None else None,
                  data_origin="REAL")
    db.add(inv)
    db.commit()
    return inv


def test_record_partial_then_full_payment(db):
    inv = _invoice(db, total=1000.0)
    r1 = rc.record_payment(db, invoice_id=inv.id, amount=400, method="transfer")
    assert r1["status"] == "OK"
    assert r1["balance"] == 600.0 and r1["payment_status"] == "PARTIAL"

    r2 = rc.record_payment(db, invoice_id=inv.id, amount=600, method="cash")
    assert r2["balance"] == 0.0 and r2["payment_status"] == "PAID"

    db.refresh(inv)
    assert inv.amount_paid == 1000.0 and inv.payment_status == "PAID"


def test_overpayment_rejected(db):
    inv = _invoice(db, total=500.0)
    r = rc.record_payment(db, invoice_id=inv.id, amount=600)
    assert r["status"] == "ERROR" and "exceeds" in r["error"]
    assert rc.balance(inv) == 500.0  # unchanged


def test_void_restores_balance(db):
    inv = _invoice(db, total=1000.0)
    p = rc.record_payment(db, invoice_id=inv.id, amount=1000)
    db.refresh(inv)
    assert inv.payment_status == "PAID"
    rc.void_payment(db, p["payment_id"])
    db.refresh(inv)
    assert inv.payment_status == "UNPAID" and rc.balance(inv) == 1000.0


def test_summary_and_aging(db):
    cust = Customer(code="DBTR", name="Debtor Co")
    db.add(cust)
    db.commit()
    _invoice(db, customer_id=cust.id, total=1000.0, days_ago=5)     # current-ish (5d)
    _invoice(db, customer_id=cust.id, total=2000.0, days_ago=45)    # 31-60
    old = _invoice(db, customer_id=cust.id, total=500.0, days_ago=120)  # 90+
    rc.record_payment(db, invoice_id=old.id, amount=200)           # partial

    s = rc.receivables_summary(db)
    assert s["total_outstanding"] == 1000 + 2000 + 300
    assert s["aging"]["31-60"] == 2000.0
    assert s["aging"]["90+"] == 300.0
    assert s["debtors"][0]["customer_name"] == "Debtor Co"

    od = rc.overdue_invoices(db)
    # all three are past invoice_date (no due_date) -> overdue
    assert od["count"] == 3 and od["total"] == 3300.0


def test_customer_statement_running_balance(db):
    cust = Customer(code="STMT", name="Statement Co")
    db.add(cust)
    db.commit()
    inv = _invoice(db, customer_id=cust.id, total=1000.0, days_ago=10)
    rc.record_payment(db, invoice_id=inv.id, amount=400, paid_at=date.today())

    st = rc.customer_statement(db, cust.id)
    assert st["outstanding"] == 600.0
    assert st["events"][0]["type"] == "INVOICE" and st["events"][0]["balance"] == 1000.0
    assert st["events"][-1]["type"] == "PAYMENT" and st["events"][-1]["balance"] == 600.0


def test_receivables_api_and_tool(client, auth_headers, db):
    cust = Customer(code="APIR", name="Api Receivable")
    db.add(cust)
    db.commit()
    inv = _invoice(db, customer_id=cust.id, total=1000.0)

    h = auth_headers("STAFF")
    pay = client.post(f"/api/v1/receivables/invoices/{inv.id}/payments", headers=h,
                      json={"amount": 250, "method": "opay", "reference": "OPAY123"})
    assert pay.status_code == 200, pay.text
    assert pay.json()["balance"] == 750.0

    summ = client.get("/api/v1/receivables/summary", headers=h)
    assert summ.status_code == 200 and summ.json()["total_outstanding"] >= 750.0

    # The API used its own session; refresh the fixture session's cached rows.
    db.expire_all()

    # Benfieg tools
    from app.services.ai.tools import execute_tool
    svc = type("U", (), {"role": "OWNER", "id": 1})()  # authorized assistant user
    rec = execute_tool(db, "get_receivables", {}, user=svc)
    assert rec["total_outstanding"] >= 750.0
    bal = execute_tool(db, "get_customer_balance", {"customer": "Api Receivable"}, user=svc)
    assert bal["outstanding"] == 750.0
