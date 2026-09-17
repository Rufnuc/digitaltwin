"""Phase D hardening: privilege-escalation, password-reset, delete safety,
sensitive-field gating."""
from __future__ import annotations

from sqlalchemy import select

from app.core.security import hash_password
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceLine
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.system import AuditLog
from app.models.user import User


def _mk_user(db, email, role) -> int:
    u = User(email=email, full_name=email, hashed_password=hash_password("pw123456"), role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u.id


# --- D1: privilege escalation ----------------------------------------------
def test_admin_cannot_grant_owner_role(client, auth_headers, db):
    uid = _mk_user(db, "target@test.example.com", "STAFF")
    r = client.patch(f"/api/v1/auth/users/{uid}", headers=auth_headers("ADMIN"),
                     json={"role": "OWNER"})
    assert r.status_code == 403, r.text


def test_admin_cannot_change_own_role(client, auth_headers, db, token_factory):
    token_factory("ADMIN")  # ensures the admin user exists
    admin = db.scalar(select(User).where(User.email == "admin@test.example.com"))
    r = client.patch(f"/api/v1/auth/users/{admin.id}", headers=auth_headers("ADMIN"),
                     json={"role": "OWNER"})
    assert r.status_code == 403, r.text


def test_owner_can_grant_owner(client, auth_headers, db):
    uid = _mk_user(db, "coowner@test.example.com", "MANAGER")
    r = client.patch(f"/api/v1/auth/users/{uid}", headers=auth_headers("OWNER"),
                     json={"role": "OWNER"})
    assert r.status_code == 200, r.text


def test_admin_cannot_deactivate_sole_owner(client, auth_headers, db):
    oid = _mk_user(db, "owner@test.example.com", "OWNER")
    r = client.patch(f"/api/v1/auth/users/{oid}", headers=auth_headers("ADMIN"),
                     json={"is_active": False})
    assert r.status_code == 403, r.text  # more privileged than the admin


# --- D2: password-reset guard ----------------------------------------------
def test_admin_cannot_reset_owner_password(client, auth_headers, db):
    oid = _mk_user(db, "owner2@test.example.com", "OWNER")
    r = client.patch(f"/api/v1/auth/users/{oid}", headers=auth_headers("ADMIN"),
                     json={"password": "newpassword123"})
    assert r.status_code == 403, r.text


def test_admin_can_reset_staff_password(client, auth_headers, db):
    sid = _mk_user(db, "staff2@test.example.com", "STAFF")
    r = client.patch(f"/api/v1/auth/users/{sid}", headers=auth_headers("ADMIN"),
                     json={"password": "newpassword123"})
    assert r.status_code == 200, r.text


def test_password_hash_never_in_audit(client, auth_headers, db):
    sid = _mk_user(db, "staff3@test.example.com", "STAFF")
    client.patch(f"/api/v1/auth/users/{sid}", headers=auth_headers("ADMIN"),
                 json={"full_name": "Renamed", "password": "newpassword123"})
    rows = db.scalars(select(AuditLog).where(AuditLog.entity_type == "users")).all()
    for row in rows:
        for payload in (row.old_value or {}, row.new_value or {}):
            assert "hashed_password" not in payload


# --- D3: delete safety ------------------------------------------------------
def test_delete_referenced_product_refused(client, auth_headers, db):
    p = Product(code="DELP", name="Del Product", purchase_cost=100, selling_price=200)
    db.add(p)
    db.commit()
    inv = Invoice(invoice_number="DREF-1", invoice_date=__import__("datetime").date(2026, 1, 1),
                  total=200)
    inv.lines.append(InvoiceLine(product_id=p.id, quantity=1, unit_price=200, line_total=200))
    db.add(inv)
    db.commit()
    r = client.delete(f"/api/v1/products/{p.id}", headers=auth_headers("MANAGER"))
    assert r.status_code == 409, r.text
    assert db.get(Product, p.id) is not None  # not destroyed


def test_delete_unreferenced_customer_archives(client, auth_headers, db):
    c = Customer(code="ARCH-1", name="Archive Me")
    db.add(c)
    db.commit()
    cid = c.id
    r = client.delete(f"/api/v1/customers/{cid}", headers=auth_headers("MANAGER"))
    assert r.status_code == 204, r.text
    db.expire_all()
    still = db.get(Customer, cid)
    assert still is not None and still.status == "ARCHIVED"  # soft-deleted, not gone


def test_delete_referenced_customer_refused(client, auth_headers, db):
    c = Customer(code="CREF-1", name="Has Invoice")
    db.add(c)
    db.commit()
    inv = Invoice(invoice_number="CREF-INV", invoice_date=__import__("datetime").date(2026, 1, 1),
                  customer_id=c.id, total=100)
    db.add(inv)
    db.commit()
    r = client.delete(f"/api/v1/customers/{c.id}", headers=auth_headers("MANAGER"))
    assert r.status_code == 409, r.text


# --- D4: sensitive-field gating --------------------------------------------
def test_staff_cannot_change_supplier_reliability(client, auth_headers, db):
    s = Supplier(code="SUP-D", name="Grader")
    db.add(s)
    db.commit()
    r = client.patch(f"/api/v1/suppliers/{s.id}", headers=auth_headers("STAFF"),
                     json={"reliability_score": 0.99})
    assert r.status_code == 403, r.text


def test_manager_can_change_supplier_reliability(client, auth_headers, db):
    s = Supplier(code="SUP-E", name="Grader2")
    db.add(s)
    db.commit()
    r = client.patch(f"/api/v1/suppliers/{s.id}", headers=auth_headers("MANAGER"),
                     json={"reliability_score": 0.88})
    assert r.status_code == 200, r.text
