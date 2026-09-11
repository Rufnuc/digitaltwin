"""Auth + RBAC tests (spec §37)."""
from __future__ import annotations

from app.core.enums import Role
from app.core.security import role_at_least


def test_role_hierarchy():
    assert role_at_least(Role.ADMIN, Role.VIEWER)
    assert role_at_least(Role.MANAGER, Role.ANALYST)
    assert not role_at_least(Role.VIEWER, Role.STAFF)
    assert role_at_least(Role.STAFF, Role.STAFF)


def test_unauthenticated_request_rejected(client):
    assert client.get("/api/v1/customers").status_code == 401


def test_login_and_me(client, db):
    from app.core.security import hash_password
    from app.models.user import User

    if not db.query(User).filter_by(email="owner@test.example.com").first():
        db.add(User(email="owner@test.example.com", full_name="Owner",
                    hashed_password=hash_password("secret123"), role="OWNER"))
        db.commit()

    r = client.post("/api/v1/auth/login",
                    json={"email": "owner@test.example.com", "password": "secret123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "OWNER"


def test_viewer_cannot_create_customer(client, auth_headers):
    r = client.post("/api/v1/customers",
                    headers=auth_headers("VIEWER"),
                    json={"code": "CX1", "name": "Blocked"})
    assert r.status_code == 403


def test_staff_can_create_customer(client, auth_headers):
    r = client.post("/api/v1/customers",
                    headers=auth_headers("STAFF"),
                    json={"code": "CX-STAFF", "name": "Allowed"})
    assert r.status_code == 201, r.text
    assert r.json()["data_origin"] == "REAL"  # user-entered => REAL, not DEMO
