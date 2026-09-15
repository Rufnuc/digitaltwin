"""Quant Phase 1 — weekly→daily forecast bridge (spec v4 §5.1)."""
from __future__ import annotations

from datetime import date, timedelta

from app.services.quant import bridge as br
from app.services.quant.demand import DemandEvent

from .golden_utils import assert_golden

AS_OF = date(2026, 3, 1)  # a Sunday


def _mondays_back(n: int) -> date:
    """The Monday n weeks before the week containing AS_OF."""
    week_start = AS_OF - timedelta(days=AS_OF.weekday())
    return week_start - timedelta(weeks=n)


def test_uniform_when_no_evidence():
    wp = br.weekday_proportions([DemandEvent(date(2026, 2, 23), 5.0)], AS_OF)
    assert wp["method"] == "uniform"
    assert wp["eligible"] is False
    assert all(abs(p - 1 / 7) <= 1e-12 for p in wp["proportions"])


def test_weekly_to_daily_sums_to_weekly_mean():
    # Q-012: uniform shares 1/7 and the daily means sum to the weekly mean.
    daily = br.weekly_to_daily(14.0)  # uniform
    assert daily == [2.0] * 7
    assert abs(sum(daily) - 14.0) <= 1e-8

    # Arbitrary (normalised) proportions still preserve the weekly total.
    props = [0.30, 0.20, 0.10, 0.10, 0.10, 0.10, 0.10]
    daily2 = br.weekly_to_daily(20.0, props)
    assert abs(sum(daily2) - 20.0) <= 1e-8


def test_empirical_when_enough_evidence():
    # 10 complete weeks; every weekday sells every week (>=3 obs per weekday),
    # but Mondays sell more, so proportions must be non-uniform and Monday largest.
    events: list[DemandEvent] = []
    for wk in range(1, 11):  # 10 full weeks before AS_OF's week
        monday = _mondays_back(wk)
        for wd in range(7):
            qty = 10.0 if wd == 0 else 2.0  # Monday-heavy
            events.append(DemandEvent(monday + timedelta(days=wd), qty))

    wp = br.weekday_proportions(events, AS_OF)
    assert wp["method"] == "empirical"
    assert wp["eligible"] is True
    assert wp["complete_weeks"] >= br.MIN_COMPLETE_WEEKS
    assert abs(sum(wp["proportions"]) - 1.0) <= 1e-8
    # Monday (index 0) is the biggest share.
    assert wp["proportions"][0] == max(wp["proportions"])

    daily = br.weekly_to_daily(22.0, wp["proportions"])
    assert abs(sum(daily) - 22.0) <= 1e-8


def test_sparse_weekday_falls_back_to_uniform():
    # 10 weeks but Sundays never sell -> a weekday has <3 obs -> uniform fallback.
    events: list[DemandEvent] = []
    for wk in range(1, 11):
        monday = _mondays_back(wk)
        for wd in range(6):  # Mon..Sat only
            events.append(DemandEvent(monday + timedelta(days=wd), 3.0))
    wp = br.weekday_proportions(events, AS_OF)
    assert wp["method"] == "uniform"
    assert wp["reason"] == "SPARSE_WEEKDAYS"


def test_incomplete_current_week_not_counted():
    # as_of mid-week: the partial current week must not be counted. The window
    # first..as_of spans two fully-elapsed weeks, so complete_weeks == 2 (not 3).
    wednesday = date(2026, 3, 4)  # Wednesday, weekday 2
    events = [DemandEvent(_mondays_back(1), 1.0)]
    wp = br.weekday_proportions(events, wednesday)
    assert wp["complete_weeks"] == 2
    assert wp["method"] == "uniform"  # well under the 8-week threshold


def test_bridge_golden_uniform():
    events = [DemandEvent(date(2026, 2, 20), 6.0), DemandEvent(date(2026, 2, 24), 8.0)]
    result = br.daily_bridge(14.0, events, AS_OF)
    assert_golden("weekly_daily_bridge", result)
