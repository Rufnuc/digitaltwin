"""Background maintenance loop.

Runs light housekeeping on an interval — currently sweeping stranded idempotency
reservations (requests that reserved a key then died before completing). The
reclaim-on-retry path in ``idempotency.reserve`` already keeps the system correct;
this sweep just stops dead rows from accumulating. Completed keys are never touched,
so replay protection is preserved.
"""
from __future__ import annotations

import asyncio
import logging

from app.db.session import SessionLocal
from app.services import idempotency

logger = logging.getLogger("digitaltwin.maintenance")

_task: asyncio.Task | None = None
DEFAULT_INTERVAL_SECONDS = 3600  # hourly


def _sweep_once() -> None:
    db = SessionLocal()
    try:
        removed = idempotency.cleanup_stranded(db)
        if removed:
            logger.info("maintenance: removed %d stranded idempotency key(s)", removed)
    finally:
        db.close()


async def _run(interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            # Run the (blocking) DB work off the event loop.
            await asyncio.to_thread(_sweep_once)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("maintenance sweep failed")


def start(interval: int = DEFAULT_INTERVAL_SECONDS) -> None:
    """Start the maintenance loop (idempotent — a second call is a no-op)."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_run(interval))


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
