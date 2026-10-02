"""User location tracking (GIS): record fixes, write meaningful moves to the activity
log, and read latest positions + history for the live map. Coordinates are
reverse-geocoded to a human address so the map and activity log read as places."""
from __future__ import annotations

import logging
import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.location import UserLocation
from app.models.user import User
from app.services import audit

logger = logging.getLogger("digitaltwin.geo")

# Small in-process cache of reverse-geocode results, keyed by coarse coordinates,
# to respect Nominatim's rate limit and avoid repeat lookups near the same spot.
_geo_cache: dict[tuple[float, float], str | None] = {}


def reverse_geocode(lat: float, lng: float) -> str | None:
    """Resolve coordinates to a readable address via OpenStreetMap Nominatim. Returns
    None (caller falls back to coordinates) if disabled or unreachable."""
    if not settings.GEO_REVERSE_GEOCODE:
        return None
    key = (round(lat, 4), round(lng, 4))  # ~11 m buckets
    if key in _geo_cache:
        return _geo_cache[key]
    import httpx

    ua = f"DigitalTwin/1.0 ({settings.GEO_GEOCODER_EMAIL or 'admin@urbanbuilds.com.ng'})"
    try:
        r = httpx.get(
            settings.GEO_GEOCODER_URL,
            params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 18,
                    "addressdetails": 0},
            headers={"User-Agent": ua}, timeout=6.0,
        )
        r.raise_for_status()
        addr = (r.json() or {}).get("display_name")
    except Exception as e:  # noqa: BLE001 — never let geocoding break a ping
        logger.warning("reverse geocode failed: %s", e)
        addr = None
    _geo_cache[key] = addr
    return addr


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points, in metres."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _last(db: Session, user_id: int) -> UserLocation | None:
    return db.scalar(
        select(UserLocation).where(UserLocation.user_id == user_id)
        .order_by(UserLocation.recorded_at.desc(), UserLocation.id.desc()).limit(1)
    )


def record_ping(db: Session, *, user: User, lat: float, lng: float,
                accuracy: float | None = None, address: str | None = None,
                source: str = "web") -> dict:
    """Store a position if it is new enough / far enough from the last, and log a
    meaningful move (with its address) to the activity trail. Returns what happened."""
    last = _last(db, user.id)
    moved = None
    if last is not None:
        moved = haversine_m(float(last.lat), float(last.lng), lat, lng)
        elapsed = 1e9
        if last.recorded_at is not None:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            ts = last.recorded_at if last.recorded_at.tzinfo else last.recorded_at.replace(tzinfo=timezone.utc)
            elapsed = (now - ts).total_seconds()
        # Skip near-duplicate pings: not moved much and logged recently.
        if moved < settings.GEO_MIN_MOVE_METERS and elapsed < settings.GEO_MIN_INTERVAL_SECONDS:
            return {"status": "SKIPPED", "moved_m": round(moved, 1)}

    # Prefer the address the browser resolved; else resolve it server-side.
    resolved = address or reverse_geocode(lat, lng)
    row = UserLocation(user_id=user.id, lat=lat, lng=lng, accuracy=accuracy,
                       address=resolved, source=source)
    db.add(row)
    db.flush()

    logged = False
    if last is None or (moved is not None and moved >= settings.GEO_LOG_MOVE_METERS):
        name = user.full_name or user.email
        where = f" — {resolved}" if resolved else f" (near {lat:.5f}, {lng:.5f})"
        summary = (f"{name} location set{where}" if last is None
                   else f"{name} moved ~{int(moved)}m{where}")
        audit.record(
            db, action="LOCATION", user_id=user.id, entity_type="user_location",
            entity_id=row.id,
            new_value={"lat": lat, "lng": lng, "accuracy": accuracy, "address": resolved},
            summary=summary, commit=False,
        )
        logged = True

    db.commit()
    return {"status": "RECORDED", "id": row.id, "address": resolved,
            "moved_m": round(moved, 1) if moved is not None else None, "logged": logged}


def latest_per_user(db: Session) -> list[dict]:
    """Each user's most recent fix — the pins for the live map."""
    # Latest row per user by id (monotonic with insertion — robust even when two
    # fixes share the same recorded_at second).
    sub = (
        select(func.max(UserLocation.id).label("mx"))
        .group_by(UserLocation.user_id).subquery()
    )
    rows = db.execute(
        select(UserLocation, User.full_name, User.email, User.role)
        .join(sub, UserLocation.id == sub.c.mx)
        .join(User, User.id == UserLocation.user_id)
        .order_by(UserLocation.recorded_at.desc())
    ).all()
    out = []
    for loc, full_name, email, role in rows:
        out.append({
            "user_id": loc.user_id, "user_name": full_name or email, "role": role,
            "lat": float(loc.lat), "lng": float(loc.lng),
            "accuracy": float(loc.accuracy) if loc.accuracy is not None else None,
            "address": loc.address,
            "recorded_at": loc.recorded_at.isoformat() if loc.recorded_at else None,
        })
    return out


def history(db: Session, *, user_id: int, limit: int = 200) -> list[dict]:
    rows = db.scalars(
        select(UserLocation).where(UserLocation.user_id == user_id)
        .order_by(UserLocation.recorded_at.desc()).limit(limit)
    ).all()
    return [{
        "lat": float(r.lat), "lng": float(r.lng),
        "accuracy": float(r.accuracy) if r.accuracy is not None else None,
        "address": r.address,
        "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
    } for r in rows]
