"""GIS user-location tracking: record, dedup, activity-log on move, reads."""
from __future__ import annotations

from app.models.system import AuditLog
from app.models.user import User
from app.services import locations


def _user(db) -> User:
    u = db.query(User).filter_by(email="staff@test.example.com").first()
    if u is None:
        from app.core.security import hash_password
        u = User(email="staff@test.example.com", full_name="Field Staff",
                 hashed_password=hash_password("pw123456"), role="STAFF")
        db.add(u)
        db.commit()
    return u


def test_haversine_known_distance():
    # ~111 km per degree of latitude.
    d = locations.haversine_m(6.0, 3.0, 7.0, 3.0)
    assert 110_000 < d < 112_000


def test_first_ping_records_and_logs(db):
    u = _user(db)
    res = locations.record_ping(db, user=u, lat=6.5244, lng=3.3792, accuracy=10)
    assert res["status"] == "RECORDED"
    assert res["logged"] is True
    logs = db.query(AuditLog).filter_by(action="LOCATION", user_id=u.id).all()
    assert len(logs) == 1


def test_small_move_is_skipped_big_move_logged(db):
    u = _user(db)
    locations.record_ping(db, user=u, lat=6.5244, lng=3.3792)
    # A ~5 m nudge within the interval → skipped (no new row, no log).
    res_small = locations.record_ping(db, user=u, lat=6.52444, lng=3.37922)
    assert res_small["status"] == "SKIPPED"
    # A clear move (~1.5 km) → recorded and logged.
    res_big = locations.record_ping(db, user=u, lat=6.5100, lng=3.3792)
    assert res_big["status"] == "RECORDED"
    assert res_big["logged"] is True
    logs = db.query(AuditLog).filter_by(action="LOCATION", user_id=u.id).count()
    assert logs == 2  # first fix + the big move


def test_latest_and_history(db):
    u = _user(db)
    locations.record_ping(db, user=u, lat=6.5244, lng=3.3792)
    locations.record_ping(db, user=u, lat=6.5100, lng=3.3792)
    latest = locations.latest_per_user(db)
    mine = next(x for x in latest if x["user_id"] == u.id)
    assert abs(mine["lat"] - 6.5100) < 1e-6  # most recent fix
    hist = locations.history(db, user_id=u.id)
    assert len(hist) >= 2
