"""Automatic, complete audit trail via SQLAlchemy flush events.

Registers session listeners that record EVERY create / update / delete on business
tables into `audit_logs`, with the acting user, the source, and the exact
before→after values — no per-endpoint code needed. High-frequency machine tables
(the AIS vessel feed, notifications, bulk market ingestion) and the audit table
itself are excluded so the trail stays about what people and the app actually did.

Timing: changes are captured in `before_flush`; the audit rows are written in
`after_flush` (when new primary keys exist) and persist with the same transaction,
so the trail commits or rolls back together with the change it describes.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import inspect
from sqlalchemy.event import listen
from sqlalchemy.orm import Session

from app.models.system import AuditLog

# The acting user and source travel on the Session's `info` dict (set by
# get_current_user / the AI assistant). Session-scoped, so it is correct regardless
# of FastAPI's dependency/endpoint threading (contextvars do not survive that).
ACTOR_KEY = "audit_actor_id"
SOURCE_KEY = "audit_source"

# Tables we do NOT audit: the audit log itself (recursion) and high-volume,
# machine-generated feeds that would drown the trail.
EXCLUDED_TABLES = {
    "audit_logs", "vessel_tracks", "notifications", "economic_data", "market_events",
    "idempotency_keys",
}
# Columns never worth diffing (they change on every write) or never safe to store:
# secrets must never land in the audit trail's old/new payloads.
_IGNORED_COLS = {"created_at", "updated_at", "hashed_password"}


def _jsonable(value):
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _pk(obj) -> int | None:
    """The object's integer primary key, read straight off the attribute (the
    identity map isn't populated yet inside after_flush, but the PK attribute is)."""
    try:
        pk_cols = inspect(obj).mapper.primary_key
        if len(pk_cols) == 1:
            val = getattr(obj, pk_cols[0].key, None)
            if isinstance(val, int):
                return val
    except Exception:  # noqa: BLE001
        return None
    return None


def _column_values(obj) -> dict:
    mapper = inspect(obj).mapper
    out = {}
    for col in mapper.columns:
        if col.key in _IGNORED_COLS:
            continue
        out[col.key] = _jsonable(getattr(obj, col.key, None))
    return out


def _changed_values(obj) -> tuple[dict, dict]:
    """(old, new) of the columns that actually changed on an update."""
    state = inspect(obj)
    old, new = {}, {}
    for col in state.mapper.columns:
        if col.key in _IGNORED_COLS:
            continue
        hist = state.attrs[col.key].history
        if not hist.has_changes():
            continue
        old[col.key] = _jsonable(hist.deleted[0]) if hist.deleted else None
        new[col.key] = _jsonable(hist.added[0]) if hist.added else None
    return old, new


def _entity_type(obj) -> str:
    return obj.__tablename__


def _before_flush(session: Session, flush_context, instances) -> None:
    """Capture what changed, keyed to the object, before PKs/SQL are emitted."""
    buffer = session.info.setdefault("_audit_buffer", [])

    for obj in session.new:
        if obj.__tablename__ in EXCLUDED_TABLES or isinstance(obj, AuditLog):
            continue
        buffer.append((obj, "CREATE", None, _column_values(obj)))

    for obj in session.dirty:
        if obj.__tablename__ in EXCLUDED_TABLES or isinstance(obj, AuditLog):
            continue
        if not session.is_modified(obj, include_collections=False):
            continue
        old, new = _changed_values(obj)
        if not new:  # only ignored columns changed → nothing worth recording
            continue
        buffer.append((obj, "UPDATE", old, new))

    for obj in session.deleted:
        if obj.__tablename__ in EXCLUDED_TABLES or isinstance(obj, AuditLog):
            continue
        buffer.append((obj, "DELETE", _column_values(obj), None))


def _after_flush(session: Session, flush_context) -> None:
    """PKs now exist — write the audit rows into the same transaction.

    Uses a Core INSERT on the session's connection rather than adding ORM objects:
    ORM objects added during after_flush are not re-flushed by the enclosing commit,
    whereas a Core insert lands immediately in the same transaction (and rolls back
    with it). Column defaults (timestamps) are applied by Core.
    """
    buffer = session.info.pop("_audit_buffer", None)
    if not buffer:
        return
    user_id = session.info.get(ACTOR_KEY)
    source = session.info.get(SOURCE_KEY, "api")
    rows = []
    for obj, action, old, new in buffer:
        entity_type = _entity_type(obj)
        entity_id = _pk(obj)
        if action == "CREATE":
            new = _column_values(obj)  # recompute now that the PK is assigned
        summary = f"{action} {entity_type}" + (f" #{entity_id}" if entity_id else "")
        rows.append({
            "user_id": user_id, "action": action, "entity_type": entity_type,
            "entity_id": entity_id, "old_value": old or None, "new_value": new or None,
            "source": source, "summary": summary[:512],
        })
    if rows:
        session.connection().execute(AuditLog.__table__.insert(), rows)


_registered = False


def register_audit_listeners() -> None:
    """Idempotently attach the auto-audit listeners to every Session."""
    global _registered
    if _registered:
        return
    listen(Session, "before_flush", _before_flush)
    listen(Session, "after_flush", _after_flush)
    _registered = True
