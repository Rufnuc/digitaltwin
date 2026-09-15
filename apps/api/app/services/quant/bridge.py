"""Weekly→daily forecast bridge (spec v4 §5.1, Phase 1).

The forecasts are weekly; the inventory-policy simulation (Phase 2) runs daily.
This module maps a weekly expected value onto seven per-weekday expected means,
so daily draws aggregate back to the weekly forecast in expectation.

Rule (v4 §5.1), authoritative:
  - Baseline is uniform: each weekday gets E_week / 7.
  - If at least 8 complete weeks of daily observations exist AND every weekday
    has >= 3 observed demand days, use the empirical weekday proportions
    (units per weekday / total units), normalised to sum to 1.
  - Otherwise fall back to uniform 1/7.
  - lambda_day[d] = E_week * weekday_proportion[d]  (so the daily means sum to
    E_week exactly).

Weekdays are indexed Monday=0 … Sunday=6, matching date.weekday().

The functions here are pure and DB-free so they are unit- and golden-testable;
`product_daily_events` is the SQLAlchemy adapter.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import DataOrigin, VerificationStatus
from app.models.invoice import Invoice, InvoiceLine
from app.services.quant.demand import DemandEvent, _week_start

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MIN_COMPLETE_WEEKS = 8   # v4 §5.1
MIN_OBS_PER_WEEKDAY = 3  # v4 §5.1
UNIFORM = [1.0 / 7.0] * 7


def _complete_weeks(first_week_start: date, as_of: date) -> int:
    """Number of fully-elapsed Mon–Sun weeks in [first_week_start, as_of].

    A week counts only if its Sunday is on or before ``as_of`` (i.e. the week has
    finished), so a partial current week is never treated as evidence."""
    # Start of the last week that has fully elapsed by as_of.
    last_full_start = _week_start(as_of)
    if as_of.weekday() != 6:  # as_of is not a Sunday -> its week is incomplete
        last_full_start -= timedelta(weeks=1)
    if last_full_start < first_week_start:
        return 0
    return ((last_full_start - first_week_start).days // 7) + 1


def weekday_proportions(events: list[DemandEvent], as_of: date) -> dict:
    """Empirical weekday demand shares with the v4 §5.1 eligibility gate.

    Returns the proportions (Mon..Sun, summing to 1), the method used
    ("empirical" | "uniform"), and the evidence that drove the decision.
    """
    dated = [e for e in events if e.quantity is not None and e.quantity > 0]
    if not dated:
        return {
            "method": "uniform", "eligible": False, "proportions": list(UNIFORM),
            "complete_weeks": 0, "weekday_obs_days": [0] * 7,
            "weekday_units": [0.0] * 7, "reason": "NO_DEMAND",
        }

    first_week = _week_start(min(e.day for e in dated))
    complete_weeks = _complete_weeks(first_week, as_of)

    units_by_wd = [0.0] * 7
    obs_days_by_wd = [set() for _ in range(7)]  # distinct demand DATES per weekday
    for e in dated:
        wd = e.day.weekday()
        units_by_wd[wd] += float(e.quantity)
        obs_days_by_wd[wd].add(e.day)
    obs_counts = [len(s) for s in obs_days_by_wd]
    total = sum(units_by_wd)

    enough_weeks = complete_weeks >= MIN_COMPLETE_WEEKS
    enough_per_wd = all(c >= MIN_OBS_PER_WEEKDAY for c in obs_counts)
    eligible = enough_weeks and enough_per_wd and total > 0

    if eligible:
        proportions = [u / total for u in units_by_wd]
        method, reason = "empirical", "OK"
    else:
        proportions = list(UNIFORM)
        method = "uniform"
        reason = "INSUFFICIENT_WEEKS" if not enough_weeks else (
            "SPARSE_WEEKDAYS" if not enough_per_wd else "NO_DEMAND"
        )

    return {
        "method": method,
        "eligible": eligible,
        # Full-precision proportions (they sum to exactly 1); callers round for
        # display. Rounding here would let the daily means drift off the weekly
        # total, breaking the aggregation guarantee.
        "proportions": proportions,
        "complete_weeks": complete_weeks,
        "weekday_obs_days": obs_counts,
        "weekday_units": [round(u, 4) for u in units_by_wd],
        "reason": reason,
    }


def weekly_to_daily(e_week: float, proportions: list[float] | None = None) -> list[float]:
    """Split a weekly expected value into seven daily means (Mon..Sun).

    With any valid proportion vector that sums to 1, the daily means sum to
    ``e_week`` exactly (up to floating point)."""
    props = proportions if proportions is not None else UNIFORM
    return [round(e_week * p, 8) for p in props]


def daily_bridge(e_week: float, events: list[DemandEvent], as_of: date) -> dict:
    """Full bridge result for a weekly expected value: the chosen weekday
    proportions plus the per-weekday expected daily means."""
    wp = weekday_proportions(events, as_of)
    lambda_day = weekly_to_daily(e_week, wp["proportions"])  # from full-precision props
    return {
        "e_week": round(float(e_week), 8),
        "method": wp["method"],
        "eligible": wp["eligible"],
        "reason": wp["reason"],
        "complete_weeks": wp["complete_weeks"],
        "weekday_names": list(WEEKDAY_NAMES),
        "weekday_proportions": [round(p, 8) for p in wp["proportions"]],
        "weekday_obs_days": wp["weekday_obs_days"],
        "expected_daily_means": lambda_day,
        "expected_daily_total": round(sum(lambda_day), 8),
    }


def product_daily_events(
    db: Session, product_id: int, as_of: date | None = None, include_demo: bool = False
) -> list[DemandEvent]:
    """Per-day verified demand events for a product (one row per invoice line)."""
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
    return [DemandEvent(day=r[0], quantity=float(r[1] or 0)) for r in rows]
