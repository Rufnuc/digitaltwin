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


def test_supersede_keeps_one_row_per_category(db):
    from sqlalchemy import func, select

    from app.models.system import Notification

    seed(db)

    def count(cat: str) -> int:
        return int(db.scalar(
            select(func.count()).select_from(Notification).where(Notification.category == cat)
        ) or 0)

    # Simulate historical pile-up: several rows queued the old way (window 0).
    for i in range(4):
        notifications.notify(db, category="market_impact", title=f"{i} alerts", dedupe_hours=0)
    assert count("market_impact") == 4

    # A superseding write collapses them to exactly one, updated in place.
    kept = notifications.notify(
        db, category="market_impact", title="5 alerts", supersede=True,
    )
    assert kept is not None and count("market_impact") == 1
    assert kept.title == "5 alerts" and kept.is_read is False

    # Re-running with the SAME content changes nothing and does not re-alert.
    kept.is_read = True
    db.commit()
    again = notifications.notify(
        db, category="market_impact", title="5 alerts", supersede=True,
    )
    assert again is None and count("market_impact") == 1
    # Still read — an unchanged standing condition must not spam the bell.
    assert notifications.list_notifications(db)[0]["is_read"] is True


def test_generate_twice_does_not_pile_up(db):
    from sqlalchemy import func, select

    from app.models.system import Notification

    seed(db)
    notifications.generate(db)
    notifications.generate(db)
    notifications.generate(db)
    # Every category must have at most one live notification after repeated scans.
    rows = db.execute(
        select(Notification.category, func.count()).group_by(Notification.category)
    ).all()
    assert rows, "demo data should produce at least one notification"
    assert all(n == 1 for _, n in rows), dict(rows)


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
