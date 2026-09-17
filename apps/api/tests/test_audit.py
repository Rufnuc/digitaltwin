"""Automatic audit trail — every create/update/delete is recorded."""
from __future__ import annotations

from sqlalchemy import select

from app.models.customer import Customer
from app.models.system import AuditLog, Notification
from app.services.audit_listener import ACTOR_KEY


def _logs(db, entity_type, entity_id=None):
    stmt = select(AuditLog).where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    return db.scalars(stmt.order_by(AuditLog.id)).all()


def test_create_update_delete_are_audited(db):
    # CREATE
    c = Customer(code="AUD1", name="Audit Co", location="Lagos")
    db.add(c)
    db.commit()
    created = _logs(db, "customers", c.id)
    assert len(created) == 1
    assert created[0].action == "CREATE"
    assert created[0].new_value["name"] == "Audit Co"
    assert created[0].source == "api"

    # UPDATE — only the changed column is captured, with before→after.
    c.name = "Audit Co Ltd"
    db.commit()
    updated = [x for x in _logs(db, "customers", c.id) if x.action == "UPDATE"]
    assert len(updated) == 1
    assert updated[0].old_value == {"name": "Audit Co"}
    assert updated[0].new_value == {"name": "Audit Co Ltd"}

    # DELETE — captures the final values.
    cid = c.id
    db.delete(c)
    db.commit()
    deleted = [x for x in _logs(db, "customers", cid) if x.action == "DELETE"]
    assert len(deleted) == 1
    assert deleted[0].old_value["code"] == "AUD1"


def test_actor_is_attributed(db):
    from app.core.security import hash_password
    from app.models.user import User
    u = User(email="actor@audit.example.com", full_name="Actor",
             hashed_password=hash_password("pw123456"), role="STAFF")
    db.add(u)
    db.commit()

    db.info[ACTOR_KEY] = u.id
    c = Customer(code="AUD2", name="With Actor")
    db.add(c)
    db.commit()
    row = _logs(db, "customers", c.id)[0]
    assert row.user_id == u.id
    db.info.pop(ACTOR_KEY, None)


def test_no_change_is_not_audited(db):
    c = Customer(code="AUD3", name="NoChange")
    db.add(c)
    db.commit()
    before = len(_logs(db, "customers", c.id))
    # Re-commit with no real change -> no new UPDATE row.
    db.commit()
    assert len(_logs(db, "customers", c.id)) == before


def test_excluded_tables_not_audited(db):
    n = Notification(title="Hi", category="test", severity="info")
    db.add(n)
    db.commit()
    assert _logs(db, "notifications") == []  # notifications are excluded


def test_audit_api_and_history(client, auth_headers, db):
    # A create through the API is auto-audited and readable via the activity log.
    h = auth_headers("MANAGER")
    created = client.post("/api/v1/customers", headers=h,
                          json={"name": "API Audit Co", "location": "Kano"})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]

    # Update it, then read the timeline.
    client.patch(f"/api/v1/customers/{cid}", headers=h, json={"location": "Abuja"})

    log = client.get("/api/v1/audit?entity_type=customers", headers=h)
    assert log.status_code == 200
    actions = [e["action"] for e in log.json()["items"] if e["entity_id"] == cid]
    assert "CREATE" in actions and "UPDATE" in actions
    # The acting user is attributed.
    assert any(e["user_name"] for e in log.json()["items"] if e["entity_id"] == cid)

    hist = client.get(f"/api/v1/audit/entity/customers/{cid}", headers=h)
    assert hist.status_code == 200
    events = hist.json()["events"]
    assert events[0]["action"] == "CREATE"
    upd = next(e for e in events if e["action"] == "UPDATE")
    assert upd["old_value"].get("location") == "Kano"
    assert upd["new_value"].get("location") == "Abuja"


def test_audit_requires_analyst(client, auth_headers):
    assert client.get("/api/v1/audit", headers=auth_headers("VIEWER")).status_code == 403


def test_activity_log_tool(db):
    from app.services.ai.tools import execute_tool
    c = Customer(code="TOOLA", name="Tool Audit")
    db.add(c)
    db.commit()
    svc = type("U", (), {"role": "OWNER", "id": 1})()  # authorized assistant user
    r = execute_tool(db, "get_activity_log", {"entity_type": "customers", "limit": 10},
                     user=svc)
    assert r["total_matching"] >= 1
    assert any("customers" in e["entity"] for e in r["events"])
