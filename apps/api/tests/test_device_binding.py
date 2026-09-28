"""Device binding: SALESGIRL (and any device_locked user) may only sign in from
an approved device; a new device is recorded PENDING until an admin approves it."""
from __future__ import annotations

from app.core.security import hash_password
from app.models.user import User, UserDevice


def _mkuser(db, email, role, password="pw123456", device_locked=False):
    u = User(email=email, full_name=email, hashed_password=hash_password(password),
             role=role, device_locked=device_locked)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _login(client, email, password="pw123456", device_id=None, label=None):
    body = {"email": email, "password": password}
    if device_id is not None:
        body["device_id"] = device_id
    if label is not None:
        body["device_label"] = label
    return client.post("/api/v1/auth/login", json=body)


def test_salesgirl_needs_a_device_id(client, db):
    _mkuser(db, "sg1@test.example.com", "SALESGIRL")
    r = _login(client, "sg1@test.example.com")  # no device id
    assert r.status_code == 403 and "approved device" in r.json()["detail"].lower()


def test_new_device_is_pending_then_approved(client, auth_headers, db):
    sg = _mkuser(db, "sg2@test.example.com", "SALESGIRL")
    # First attempt from a new device: recorded PENDING, login refused.
    r = _login(client, "sg2@test.example.com", device_id="dev-AAA", label="Shop laptop")
    assert r.status_code == 403
    dev = db.query(UserDevice).filter_by(user_id=sg.id, device_id="dev-AAA").first()
    assert dev is not None and dev.status == "PENDING" and dev.label == "Shop laptop"

    # Owner approves it.
    ap = client.patch(f"/api/v1/auth/users/{sg.id}/devices/{dev.id}",
                      json={"status": "APPROVED"}, headers=auth_headers("OWNER"))
    assert ap.status_code == 200 and ap.json()["status"] == "APPROVED"

    # Now the same device signs in fine…
    ok = _login(client, "sg2@test.example.com", device_id="dev-AAA")
    assert ok.status_code == 200 and ok.json()["role"] == "SALESGIRL"
    # …but a different device is still refused.
    other = _login(client, "sg2@test.example.com", device_id="dev-BBB")
    assert other.status_code == 403


def test_blocked_device_refused(client, auth_headers, db):
    sg = _mkuser(db, "sg3@test.example.com", "SALESGIRL")
    _login(client, "sg3@test.example.com", device_id="dev-C")
    dev = db.query(UserDevice).filter_by(user_id=sg.id, device_id="dev-C").first()
    client.patch(f"/api/v1/auth/users/{sg.id}/devices/{dev.id}",
                 json={"status": "APPROVED"}, headers=auth_headers("OWNER"))
    assert _login(client, "sg3@test.example.com", device_id="dev-C").status_code == 200
    # Block it → refused again.
    client.patch(f"/api/v1/auth/users/{sg.id}/devices/{dev.id}",
                 json={"status": "BLOCKED"}, headers=auth_headers("OWNER"))
    r = _login(client, "sg3@test.example.com", device_id="dev-C")
    assert r.status_code == 403 and "blocked" in r.json()["detail"].lower()


def test_unlocked_user_not_gated(client, db):
    _mkuser(db, "staff1@test.example.com", "STAFF")
    # No device id, not device_locked, not salesgirl → normal login.
    assert _login(client, "staff1@test.example.com").status_code == 200


def test_device_lock_toggle_gates_any_user(client, auth_headers, db):
    u = _mkuser(db, "staff2@test.example.com", "STAFF")
    assert _login(client, "staff2@test.example.com").status_code == 200
    # Owner turns on device lock for this STAFF user.
    client.patch(f"/api/v1/auth/users/{u.id}", json={"device_locked": True},
                 headers=auth_headers("OWNER"))
    assert _login(client, "staff2@test.example.com", device_id="d1").status_code == 403
