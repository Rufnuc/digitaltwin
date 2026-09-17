"""Reserve-first idempotency for money/stock-moving writes.

Usage in an endpoint::

    reserved = idempotency.reserve(db, key, scope="sell")
    if reserved.replay is not None:
        return reserved.replay          # a completed original — return it verbatim
    if reserved.in_progress:
        raise HTTPException(409, "request already in progress")
    ... do the write, build `result` ...
    idempotency.complete(db, key, result)   # stores the response, commits
    return result

If ``key`` is None the caller opts out and the write proceeds without protection
(the invoice-number unique constraint is still a backstop for sales).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyKey

# A reservation with no stored response older than this is treated as STRANDED (the
# original request died before completing) and may be reclaimed by a retry. It is set
# well above any real request duration so a still-running original is never reclaimed
# (which would allow a duplicate write). Completed keys (with a response) never expire.
STRANDED_TTL = timedelta(minutes=2)


@dataclass
class Reservation:
    replay: dict | None      # the original completed response, if any
    in_progress: bool        # key exists but the original hasn't finished


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def reserve(db: Session, key: str | None, *, scope: str) -> Reservation:
    """Claim the key. Returns the stored response on a replay, flags an in-flight
    duplicate, reclaims a stranded reservation, or reserves the key for a first-time
    request."""
    if not key:
        return Reservation(replay=None, in_progress=False)
    existing = db.get(IdempotencyKey, key)
    if existing is not None:
        if existing.response_json is not None:
            # Completed: always a safe replay, never expires.
            return Reservation(replay=existing.response_json, in_progress=False)
        # Reserved but not completed. If the original is still within the TTL it is a
        # live duplicate; if older, the original died — reclaim it for this retry.
        if _now() - _aware(existing.created_at) <= STRANDED_TTL:
            return Reservation(replay=None, in_progress=True)
        existing.created_at = _now()
        existing.scope = scope
        db.flush()
        return Reservation(replay=None, in_progress=False)
    db.add(IdempotencyKey(key=key, scope=scope, response_json=None))
    try:
        db.flush()
    except IntegrityError:
        # Lost the race to another identical request that inserted first.
        db.rollback()
        again = db.get(IdempotencyKey, key)
        if again is not None and again.response_json is not None:
            return Reservation(replay=again.response_json, in_progress=False)
        return Reservation(replay=None, in_progress=True)
    return Reservation(replay=None, in_progress=False)


def complete(db: Session, key: str | None, response: dict) -> None:
    """Store the successful response against a previously reserved key and commit."""
    if not key:
        return
    row = db.get(IdempotencyKey, key)
    if row is not None:
        # Store a JSON-safe copy (Decimals/dates → primitives) so a replay returns
        # exactly the values the original response carried.
        row.response_json = jsonable_encoder(response)
    db.commit()


def cleanup_stranded(db: Session, older_than: timedelta = STRANDED_TTL) -> int:
    """Delete reservations that were never completed and are older than the TTL — a
    safety-net sweep. Completed keys (with a stored response) are always kept, so
    replay protection is never lost. Returns the number removed."""
    cutoff = _now() - older_than
    # Age is compared in Python so the result is identical on Postgres and SQLite
    # (which stores naive/aware datetimes inconsistently). Only never-completed keys
    # are eligible; completed keys keep their replay value forever.
    incomplete = db.scalars(
        select(IdempotencyKey).where(IdempotencyKey.response_json.is_(None))
    ).all()
    stale = [r.key for r in incomplete if _aware(r.created_at) < cutoff]
    if stale:
        db.execute(delete(IdempotencyKey).where(IdempotencyKey.key.in_(stale)))
        db.commit()
    return len(stale)
