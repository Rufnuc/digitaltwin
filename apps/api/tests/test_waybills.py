"""Waybills: dispatch records linked to invoices."""
from __future__ import annotations

from datetime import date

import pytest

from app.models.customer import Customer
from app.models.invoice import Invoice


@pytest.fixture
def invoice(db):
    c = Customer(code="WB-C", name="Dispatch Buyer")
    db.add(c)
    db.commit()
    inv = Invoice(invoice_number="WB-INV-1", invoice_date=date(2026, 1, 1),
                  customer_id=c.id, total=50000)
    db.add(inv)
    db.commit()
    return inv.id


def test_create_waybill_links_invoice_and_autonumbers(client, auth_headers, invoice):
    r = client.post("/api/v1/waybills", headers=auth_headers("STAFF"), json={
        "invoice_id": invoice, "apprentice_name": "Chidi", "transport_company": "GUO",
        "driver_phone": "08030000000", "station": "Iddo Park",
        "destination": "Kano", "receiver_name": "Bello",
    })
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["waybill_number"].startswith("WB-") and b["status"] == "PENDING"
    assert b["invoice_number"] == "WB-INV-1" and b["customer_name"] == "Dispatch Buyer"
    assert b["apprentice_name"] == "Chidi" and b["transport_company"] == "GUO"
    assert b["station"] == "Iddo Park" and b["destination"] == "Kano"
    assert b["dispatched_at"] is None


def test_create_waybill_bad_invoice_404(client, auth_headers):
    r = client.post("/api/v1/waybills", headers=auth_headers("STAFF"),
                    json={"invoice_id": 99999})
    assert r.status_code == 404, r.text


def test_dispatch_stamps_time_and_status(client, auth_headers, invoice):
    wid = client.post("/api/v1/waybills", headers=auth_headers("STAFF"),
                      json={"invoice_id": invoice}).json()["id"]
    r = client.patch(f"/api/v1/waybills/{wid}", headers=auth_headers("STAFF"),
                     json={"status": "DISPATCHED", "apprentice_name": "Ade"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "DISPATCHED" and b["dispatched_at"] is not None
    assert b["apprentice_name"] == "Ade"


def test_invalid_status_rejected(client, auth_headers, invoice):
    wid = client.post("/api/v1/waybills", headers=auth_headers("STAFF"),
                      json={"invoice_id": invoice}).json()["id"]
    r = client.patch(f"/api/v1/waybills/{wid}", headers=auth_headers("STAFF"),
                     json={"status": "TELEPORTED"})
    assert r.status_code == 400, r.text


def test_list_filters_by_status_and_invoice(client, auth_headers, invoice):
    a = client.post("/api/v1/waybills", headers=auth_headers("STAFF"),
                    json={"invoice_id": invoice}).json()["id"]
    client.patch(f"/api/v1/waybills/{a}", headers=auth_headers("STAFF"),
                 json={"status": "DELIVERED"})
    client.post("/api/v1/waybills", headers=auth_headers("STAFF"), json={"invoice_id": invoice})
    # Two waybills on the invoice; one DELIVERED.
    by_inv = client.get(f"/api/v1/waybills?invoice_id={invoice}", headers=auth_headers("STAFF"))
    assert by_inv.json()["total"] == 2
    delivered = client.get("/api/v1/waybills?status=DELIVERED", headers=auth_headers("STAFF"))
    assert delivered.json()["total"] == 1


def test_waybill_requires_staff(client, auth_headers, invoice):
    r = client.post("/api/v1/waybills", headers=auth_headers("VIEWER"),
                    json={"invoice_id": invoice})
    assert r.status_code == 403, r.text
