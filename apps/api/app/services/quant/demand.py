"""Demand-observation extraction (spec v4 §5, Phase 1).

Turns verified sales into an aligned weekly demand series per product — the input
to classification, forecasting and reorder. Only VERIFIED invoice lines with a
resolved product and non-negative quantity are counted (spec v4 §3.1); demo rows
are excluded unless explicitly requested.

The pure functions (`weekly_buckets`, `nonzero_stats`) are DB-free and golden-
testable; `product_weekly_demand` is the SQLAlchemy adapter.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import DataOrigin, VerificationStatus
from app.models.invoice import Invoice, InvoiceLine


@dataclass(frozen=True)
class DemandEvent:
    day: date
    quantity: float


def _week_start(d: date) -> date:
    """Monday of the ISO week containing d."""
    return d - timedelta(days=d.weekday())


def weekly_buckets(
    events: list[DemandEvent], as_of: date, min_weeks: int = 0
) -> list[dict]:
    """Aligned weekly demand, oldest→newest, INCLUDING zero-demand weeks (needed for
    intermittence). The window runs from the first event's week to the week of
    ``as_of`` inclusive. If there are no events, returns an empty list."""
    dated = [e for e in events if e.quantity is not None and e.quantity >= 0]
    if not dated:
        return []
    first = _week_start(min(e.day for e in dated))
    last = _week_start(as_of)
    # Extend the start back so at least `min_weeks` buckets exist.
    n_weeks = ((last - first).days // 7) + 1
    if min_weeks and n_weeks < min_weeks:
        first = last - timedelta(weeks=min_weeks - 1)

    totals: dict[date, float] = {}
    for e in dated:
        ws = _week_start(e.day)
        if ws < first:
            continue
        totals[ws] = totals.get(ws, 0.0) + float(e.quantity)

    out: list[dict] = []
    w = first
    while w <= last:
        out.append({"week_start": w.isoformat(), "units": round(totals.get(w, 0.0), 4)})
        w += timedelta(weeks=1)
    return out


def nonzero_stats(units: list[float]) -> dict:
    """Mean/variance/CV of the non-zero demand sizes, plus counts used by ADI/CV²."""
    nz = [u for u in units if u > 0]
    n = len(units)
    if not nz:
        return {"periods": n, "nonzero_periods": 0, "nonzero_mean": None,
                "nonzero_std": None, "nonzero_cv": None, "nonzero_cv_squared": None}
    mean = statistics.fmean(nz)
    std = statistics.pstdev(nz) if len(nz) > 1 else 0.0
    cv = (std / mean) if mean else 0.0
    return {
        "periods": n,
        "nonzero_periods": len(nz),
        "nonzero_mean": round(mean, 6),
        "nonzero_std": round(std, 6),
        "nonzero_cv": round(cv, 6),
        "nonzero_cv_squared": round(cv * cv, 6),
    }


def product_weekly_demand(
    db: Session, product_id: int, as_of: date | None = None, include_demo: bool = False
) -> dict:
    """The verified weekly demand series for a product from invoice lines."""
    as_of = as_of or date.today()
    stmt = (
        select(Invoice.invoice_date, InvoiceLine.quantity)
        .join(InvoiceLine, InvoiceLine.invoice_id == Invoice.id)
        .where(
            InvoiceLine.product_id == product_id,
            Invoice.invoice_date <= as_of,
            Invoice.verification_status == VerificationStatus.VERIFIED.value,
        )
    )
    if not include_demo:
        stmt = stmt.where(Invoice.data_origin != DataOrigin.DEMO.value)
    rows = db.execute(stmt).all()
    events = [DemandEvent(day=r[0], quantity=float(r[1] or 0)) for r in rows]
    buckets = weekly_buckets(events, as_of)
    units = [b["units"] for b in buckets]
    return {
        "product_id": product_id,
        "as_of": as_of.isoformat(),
        "frequency": "WEEKLY",
        "weeks": buckets,
        "units": units,
        "total_units": round(sum(units), 4),
        "stats": nonzero_stats(units),
        "provenance": DataOrigin.REAL.value,
        "included_demo": include_demo,
    }
