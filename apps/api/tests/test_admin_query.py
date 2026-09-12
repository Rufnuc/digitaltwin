"""List querying (sort/filter/search), user management, and data management."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models.customer import Customer
from app.seed.demo_data import seed


def test_list_sort_filter_search(client, auth_headers, db):
    seed(db)
    h = auth_headers("VIEWER")

    # Sort by name, descending.
    r = client.get("/api/v1/customers?sort=name&sort_dir=desc&limit=100", headers=h)
    assert r.status_code == 200, r.text
    names = [i["name"] for i in r.json()["items"]]
    assert names == sorted(names, reverse=True)
    assert r.json()["sort"] == "name" and r.json()["sort_dir"] == "desc"

    # Filter by an arbitrary column (case-insensitive).
    r2 = client.get("/api/v1/customers?status=active&limit=100", headers=h)
    assert r2.json()["filters"] == {"status": "active"}
    assert all(i["status"] == "ACTIVE" for i in r2.json()["items"])

    # Search still works.
    r3 = client.get("/api/v1/customers?q=Customer%201", headers=h)
    assert r3.json()["total"] >= 1

    # sortable_fields is advertised for the UI.
    assert "name" in r.json()["sortable_fields"]


def test_user_management(client, auth_headers, db):
    admin = auth_headers("ADMIN")
    lst = client.get("/api/v1/auth/users", headers=admin)
    assert lst.status_code == 200 and isinstance(lst.json(), list)

    created = client.post("/api/v1/auth/users", headers=admin, json={
        "email": "newuser@example.com", "full_name": "New User",
        "password": "pw123456", "role": "STAFF"})
    assert created.status_code == 201, created.text
    uid = created.json()["id"]

    upd = client.patch(f"/api/v1/auth/users/{uid}", headers=admin,
                       json={"role": "MANAGER", "is_active": False})
    assert upd.status_code == 200
    assert upd.json()["role"] == "MANAGER" and upd.json()["is_active"] is False

    # An admin cannot deactivate themselves.
    me = client.get("/api/v1/auth/me", headers=admin).json()
    block = client.patch(f"/api/v1/auth/users/{me['id']}", headers=admin, json={"is_active": False})
    assert block.status_code == 400

    # Non-admins cannot manage users.
    assert client.get("/api/v1/auth/users", headers=auth_headers("MANAGER")).status_code == 403


def test_data_stats_and_purge_demo(client, auth_headers, db):
    seed(db)
    owner = auth_headers("OWNER")

    stats = client.get("/api/v1/admin/data-stats", headers=owner).json()
    assert stats["total_demo_rows"] > 0
    cust_row = next(t for t in stats["tables"] if t["table"] == "customers")
    assert cust_row["demo"] > 0

    # A real record must survive the purge.
    db.add(Customer(code="REAL-1", name="Real Co", data_origin="REAL"))
    db.commit()

    # Staff/Manager cannot purge; Owner can.
    denied = client.post("/api/v1/admin/purge-demo", headers=auth_headers("MANAGER"))
    assert denied.status_code == 403
    purge = client.post("/api/v1/admin/purge-demo", headers=owner)
    assert purge.status_code == 200, purge.text
    assert purge.json()["total_deleted"] > 0

    # Demo gone, real kept.
    assert db.scalar(
        select(func.count()).select_from(Customer).where(Customer.data_origin == "DEMO")
    ) == 0
    assert db.scalar(select(Customer).where(Customer.code == "REAL-1")) is not None
