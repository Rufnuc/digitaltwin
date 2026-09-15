"""Lead-time statistics (spec v4 §6 "Lead-time risk", Phase 1).

A realised lead time is the days between placing a purchase (Purchase.purchase_date)
and receiving the goods (StockLot.received_date) for lots linked to that purchase.
From the per-product sample we derive mean, standard deviation and p50/p95, and the
lead-time risk `clamp((p95 - p50) / max(p50, 1), 0, 1)`.

When there is too little history we fall back to the product's point lead-time
estimate with zero variability and mark the result ESTIMATED, so downstream safety
stock still runs but never overstates confidence.

`lead_time_stats` is pure and testable; `product_lead_time_stats` is the adapter.
"""
from __future__ import annotations

import math
import statistics
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import DataOrigin
from app.models.purchase import Purchase
from app.models.warehouse import StockLot

MIN_SAMPLES = 3  # below this we cannot estimate variability -> point fallback


def _quantile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation quantile (same convention as numpy 'linear')."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(sorted_vals[lo])
    frac = pos - lo
    return float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)


def lead_time_stats(
    samples: list[float], point_estimate: float | None = None
) -> dict:
    """Lead-time mean/std/quantiles and risk from realised samples.

    With < MIN_SAMPLES observations, fall back to ``point_estimate`` (std 0) and
    mark the source ESTIMATED. With no samples and no point estimate, return
    UNKNOWN so callers can surface a missing-input status.
    """
    clean = [float(s) for s in samples if s is not None and s >= 0]
    if len(clean) >= MIN_SAMPLES:
        srt = sorted(clean)
        mean = statistics.fmean(srt)
        std = statistics.pstdev(srt) if len(srt) > 1 else 0.0
        p50 = _quantile(srt, 0.50)
        p95 = _quantile(srt, 0.95)
        risk = min(1.0, max(0.0, (p95 - p50) / max(p50, 1.0)))
        return {
            "status": "OK", "source": "EMPIRICAL", "n": len(srt),
            "mean_days": round(mean, 4), "std_days": round(std, 4),
            "p50_days": round(p50, 4), "p95_days": round(p95, 4),
            "lead_time_risk": round(risk, 4),
        }
    if point_estimate is not None and point_estimate >= 0:
        pe = float(point_estimate)
        return {
            "status": "OK", "source": "ESTIMATED", "n": len(clean),
            "mean_days": round(pe, 4), "std_days": 0.0,
            "p50_days": round(pe, 4), "p95_days": round(pe, 4),
            "lead_time_risk": 0.0,
            "warnings": ["LEAD_TIME_POINT_ESTIMATE"],
        }
    return {"status": "UNKNOWN", "source": "NONE", "n": len(clean),
            "mean_days": None, "std_days": None, "p50_days": None,
            "p95_days": None, "lead_time_risk": None}


def realised_lead_times(
    db: Session, product_id: int, include_demo: bool = False
) -> list[float]:
    """Days between purchase_date and received_date for this product's lots."""
    stmt = (
        select(Purchase.purchase_date, StockLot.received_date)
        .join(Purchase, Purchase.id == StockLot.purchase_id)
        .where(StockLot.product_id == product_id, StockLot.purchase_id.is_not(None))
    )
    if not include_demo:
        stmt = stmt.where(StockLot.data_origin != DataOrigin.DEMO.value)
    out: list[float] = []
    for ordered, received in db.execute(stmt).all():
        if isinstance(ordered, date) and isinstance(received, date):
            days = (received - ordered).days
            if days >= 0:
                out.append(float(days))
    return out


def product_lead_time_stats(
    db: Session, product_id: int, point_estimate: float | None = None,
    include_demo: bool = False,
) -> dict:
    samples = realised_lead_times(db, product_id, include_demo=include_demo)
    return lead_time_stats(samples, point_estimate=point_estimate)
