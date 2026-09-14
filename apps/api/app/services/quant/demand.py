"""Demand-observation extraction (Quant Phase 1).

Turns verified sales records into an aligned per-period demand series that the
classifier and forecast models consume. Only VERIFIED invoice lines count as
demand evidence (spec v4 §3.1 — never treat a row as verified just because it
exists). The pure bucketing functions are separated from the DB adapter so they
can be unit-tested against golden fixtures.

Provenance: the series is REAL observed data; any imputed zero periods are the
absence of demand, not invented demand.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import VerificationStatus
from app.models.invoice import Invoice, InvoiceLine


@dataclass(frozen=True)
class DemandEvent:
    """One dated demand quantity for a product."""
    on: date
    units: float


def _week_start(d: date) -> date:
    """Monday of the ISO week containing d."""
    return d - timedelta(days=d.weekday())


def weekly_series(events: list[DemandEvent], as_of: date,
                  weeks: int | None = None) -> list[float]:
    """Aligned weekly demand totals from the first event's week to `as_of`'s week,
    inclusive, with zero-filled gaps. If `weeks` is given, return exactly the last
    `weeks` buckets (left-padded with zeros if history is shorter)."""
    if not events:
        return [0.0] * (weeks or 0)
    end = _week_start(as_of)
    first = _week_start(min(e.on for e in events))
    n = int((end - first).days // 7) + 1
    buckets = [0.0] * n
    for e in events:
        idx = int((_week_start(e.on) - first).days // 7)
        if 0 <= idx < n:
            buckets[idx] += float(e.units)
    if weeks is None:
        return buckets
    if len(buckets) >= weeks:
        return buckets[-weeks:]
    return [0.0] * (weeks - len(buckets)) + buckets


def nonzero_sizes(series: list[float]) -> list[float]:
    return [v for v in series if v > 0]


# --------------------------------------------------------------------------- #
# DB adapters
# --------------------------------------------------------------------------- #
def product_demand_events(db: Session, product_id: int, *,
                          verified_only: bool = True) -> list[DemandEvent]:
    """All demand events (sold units) for a product from invoice lines."""
    stmt = (
        select(Invoice.invoice_date, InvoiceLine.quantity)
        .join(InvoiceLine, InvoiceLine.invoice_id == Invoice.id)
        .where(InvoiceLine.product_id == product_id)
    )
    if verified_only:
        stmt = stmt.where(Invoice.verification_status == VerificationStatus.VERIFIED.value)
    return [DemandEvent(on=d, units=float(q or 0))
            for d, q in db.execute(stmt).all() if d is not None]


def product_weekly_series(db: Session, product_id: int, *, as_of: date | None = None,
                          weeks: int | None = None,
                          verified_only: bool = True) -> list[float]:
    events = product_demand_events(db, product_id, verified_only=verified_only)
    return weekly_series(events, as_of or date.today(), weeks)
