"""Tax estimate — VAT and income tax from recorded data."""
from __future__ import annotations

from datetime import date, timedelta

from app.core.enums import VerificationStatus
from app.models.expense import Expense
from app.models.invoice import Invoice, InvoiceLine
from app.models.product import Product
from app.services import tax


def test_tax_summary_vat_and_income(db):
    prod = Product(code="TXP", name="Taxable Part", purchase_cost=100.0, selling_price=200.0)
    db.add(prod)
    db.commit()

    # A sale of 10 units @ 200 = 2000 subtotal + 150 VAT; COGS = 10*100 = 1000.
    inv = Invoice(invoice_number="TAX-1", invoice_date=date.today(), currency="NGN",
                  subtotal=2000, tax=150, total=2150, data_origin="REAL",
                  verification_status=VerificationStatus.VERIFIED.value)
    inv.lines.append(InvoiceLine(product_id=prod.id, quantity=10, unit_price=200,
                                 line_total=2000))
    db.add(inv)
    db.add(Expense(expense_date=date.today(), category="rent", amount=300, currency="NGN",
                   data_origin="REAL"))
    db.commit()

    r = tax.tax_summary(db, start=date.today() - timedelta(days=30), end=date.today())
    assert r["revenue"] == 2150.0
    assert r["vat"]["output_vat"] == 150.0
    assert r["vat"]["vat_payable"] == 150.0            # no input VAT
    it = r["income_tax"]
    assert it["cost_of_goods_sold"] == 1000.0
    assert it["operating_expenses"] == 300.0
    # taxable profit = 2150 - 1000 - 300 = 850
    assert it["taxable_profit"] == 850.0
    # tiny turnover -> small-company exempt (0%)
    assert it["cit_rate"] == 0.0 and it["income_tax"] == 0.0
    assert r["total_estimated_tax"] == 150.0           # just the VAT
    assert "not tax advice" in r["disclaimer"]


def test_tax_api_and_tool(client, auth_headers, db):
    prod = Product(code="TXA", name="Api Tax Part", purchase_cost=100.0, selling_price=200.0)
    db.add(prod)
    db.commit()
    inv = Invoice(invoice_number="TAX-API", invoice_date=date.today(), currency="NGN",
                  subtotal=1000, tax=75, total=1075, data_origin="REAL",
                  verification_status=VerificationStatus.VERIFIED.value)
    inv.lines.append(InvoiceLine(product_id=prod.id, quantity=5, unit_price=200, line_total=1000))
    db.add(inv)
    db.commit()

    resp = client.get("/api/v1/tax/summary", headers=auth_headers("MANAGER"))
    assert resp.status_code == 200
    assert resp.json()["vat"]["output_vat"] >= 75.0

    from app.services.ai.tools import execute_tool
    t = execute_tool(db, "get_tax_estimate", {})
    assert "total_estimated_tax" in t and "disclaimer" in t

    # A plain staff member cannot see the tax estimate.
    assert client.get("/api/v1/tax/summary", headers=auth_headers("STAFF")).status_code == 403
