"""The restricted SALESGIRL front-desk role: what it may and may not do."""
from __future__ import annotations

from app.models.customer import Customer


def test_salesgirl_can_add_customer_but_not_delete(client, auth_headers, db):
    sg = auth_headers("SALESGIRL")
    # Add a customer.
    r = client.post("/api/v1/customers", json={"name": "Front Desk Co"}, headers=sg)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    # Can edit (front desk fixes a detail) — and it is audit-logged automatically.
    assert client.patch(f"/api/v1/customers/{cid}", json={"location": "Kano"},
                        headers=sg).status_code == 200
    # But may NOT delete.
    assert client.delete(f"/api/v1/customers/{cid}", headers=sg).status_code == 403


def test_salesgirl_can_search_and_read_customers(client, auth_headers, db):
    db.add(Customer(code="SG-R", name="Searchable Co"))
    db.commit()
    sg = auth_headers("SALESGIRL")
    assert client.get("/api/v1/customers?q=Searchable", headers=sg).status_code == 200


def test_salesgirl_can_do_invoices_and_waybills(client, auth_headers, db):
    sg = auth_headers("SALESGIRL")
    # Create an invoice.
    r = client.post("/api/v1/invoices", json={
        "invoice_number": "SG-INV-1", "invoice_date": "2026-01-01",
        "lines": [{"description": "part", "quantity": 1, "unit_price": 100}],
    }, headers=sg)
    assert r.status_code == 201, r.text
    inv_id = r.json()["id"]
    # Raise a waybill against it.
    w = client.post("/api/v1/waybills", json={"invoice_id": inv_id}, headers=sg)
    assert w.status_code == 201, w.text
    # Recording a customer payment is permitted for the front desk (not 403 — any
    # non-permission error like an amount/balance check is a separate concern).
    p = client.post(f"/api/v1/receivables/invoices/{inv_id}/payments",
                    json={"amount": 10}, headers=sg)
    assert p.status_code != 403, p.text


def test_salesgirl_blocked_from_other_modules(client, auth_headers, db):
    sg = auth_headers("SALESGIRL")
    # Cannot create products or suppliers, or touch procurement / receivables summary.
    assert client.post("/api/v1/products", json={"name": "P"}, headers=sg).status_code == 403
    assert client.post("/api/v1/suppliers", json={"code": "S1", "name": "S"},
                       headers=sg).status_code == 403
    assert client.get("/api/v1/receivables/summary", headers=sg).status_code == 403


def test_salesgirl_dashboard_hides_money(client, auth_headers, db):
    sg = auth_headers("SALESGIRL")
    d = client.get("/api/v1/dashboard/summary", headers=sg).json()
    assert d.get("money_hidden") is True
    kpis = set(d.get("kpis", {}))
    assert "revenue" not in kpis and "net_profit" not in kpis and "inventory_value" not in kpis
    # Operational counts stay visible.
    assert "orders" in kpis
    # Revenue timeseries is empty for the front desk.
    ts = client.get("/api/v1/dashboard/revenue-timeseries", headers=sg).json()
    assert ts["series"] == []
