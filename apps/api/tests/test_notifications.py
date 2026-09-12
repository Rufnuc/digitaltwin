"""Notifications: generation (deduped), listing, and read state."""
from __future__ import annotations

from app.seed.demo_data import seed
from app.services import notifications


def test_generate_creates_and_dedupes(db):
    seed(db)
    r1 = notifications.generate(db)
    assert r1["created"] >= 1  # at least churn / low-stock on the demo data
    # Churn risk exists in the demo data.
    assert "churn" in r1["categories"]

    # Running again immediately creates nothing (deduped within the window).
    r2 = notifications.generate(db)
    assert r2["created"] == 0

    assert notifications.unread_count(db) == r1["created"]


def test_list_and_mark_read(db):
    seed(db)
    notifications.generate(db)
    items = notifications.list_notifications(db)
    assert items and items[0]["is_read"] is False
    assert "created_at" in items[0] and items[0]["link"]

    before = notifications.unread_count(db)
    assert notifications.mark_read(db, items[0]["id"]) is True
    assert notifications.unread_count(db) == before - 1

    marked = notifications.mark_all_read(db)
    assert marked == before - 1
    assert notifications.unread_count(db) == 0


def test_dedupe_window_zero_allows_duplicate(db):
    seed(db)
    a = notifications.notify(db, category="test", title="One")
    b = notifications.notify(db, category="test", title="Two")  # within window -> deduped
    c = notifications.notify(db, category="test", title="Three", dedupe_hours=0)
    assert a is not None and b is None and c is not None


def test_notifications_api(client, auth_headers, db):
    seed(db)
    gen = client.post("/api/v1/notifications/generate", headers=auth_headers("VIEWER"))
    assert gen.status_code == 200 and gen.json()["created"] >= 1

    lst = client.get("/api/v1/notifications", headers=auth_headers("VIEWER"))
    assert lst.status_code == 200
    body = lst.json()
    assert body["unread_count"] >= 1 and body["items"]

    nid = body["items"][0]["id"]
    read = client.post(f"/api/v1/notifications/{nid}/read", headers=auth_headers("VIEWER"))
    assert read.status_code == 200

    count = client.get("/api/v1/notifications/unread-count", headers=auth_headers("VIEWER"))
    assert count.json()["unread_count"] == body["unread_count"] - 1

    all_read = client.post("/api/v1/notifications/read-all", headers=auth_headers("VIEWER"))
    assert all_read.status_code == 200
    final = client.get("/api/v1/notifications/unread-count", headers=auth_headers("VIEWER"))
    assert final.json()["unread_count"] == 0
