"""Quant Phase 1: demand extraction + ADI/CV² pattern + ABC classification.

Covers acceptance-matrix items for classification (ADI/CV² boundaries, ABC window
and short-history gate) and the weekly bucketing bridge inputs.
"""
from __future__ import annotations

from datetime import date

from app.services.quant.classification import (
    ABC_MIN_COVERED_DAYS,
    abc_classify,
    classify_pattern,
)
from app.services.quant.demand import DemandEvent, weekly_series


# --- weekly series -----------------------------------------------------------
def test_weekly_series_aligns_and_zero_fills():
    # Two sales three weeks apart -> [q1, 0, 0, q2] Monday-aligned.
    events = [DemandEvent(date(2026, 1, 5), 4), DemandEvent(date(2026, 1, 26), 6)]
    s = weekly_series(events, as_of=date(2026, 1, 30))
    assert s == [4.0, 0.0, 0.0, 6.0]


def test_weekly_series_last_n_padding():
    events = [DemandEvent(date(2026, 1, 5), 4)]
    s = weekly_series(events, as_of=date(2026, 1, 12), weeks=4)
    assert s == [0.0, 0.0, 4.0, 0.0]  # week of 5th has 4, week of 12th empty, left-padded


def test_no_events():
    assert weekly_series([], as_of=date(2026, 1, 1), weeks=3) == [0.0, 0.0, 0.0]


# --- pattern classification --------------------------------------------------
def test_smooth_pattern_routes_to_ses():
    r = classify_pattern([5, 5, 5, 5, 5, 5, 5, 5])
    assert r.pattern == "SMOOTH"
    assert r.adi == 1.0 and r.cv_squared == 0.0
    assert r.recommended_models[0] == "ses"


def test_intermittent_pattern_routes_to_croston():
    # Every ~4th week has demand of similar size -> high ADI, low CV².
    r = classify_pattern([0, 0, 0, 3, 0, 0, 0, 3, 0, 0, 0, 3])
    assert r.pattern == "INTERMITTENT"
    assert r.adi and r.adi >= 1.32
    assert "croston" in r.recommended_models


def test_lumpy_pattern():
    # Sparse and variable sizes -> high ADI, high CV².
    r = classify_pattern([0, 0, 1, 0, 0, 0, 10, 0, 0, 0, 0, 20])
    assert r.pattern == "LUMPY"
    assert r.adi >= 1.32 and r.cv_squared >= 0.49


def test_erratic_pattern():
    # Frequent demand but highly variable sizes -> low ADI, high CV².
    r = classify_pattern([1, 20, 1, 25, 2, 18, 1, 30])
    assert r.pattern == "ERRATIC"
    assert r.adi < 1.32 and r.cv_squared >= 0.49


def test_no_demand():
    r = classify_pattern([0, 0, 0, 0])
    assert r.pattern == "NO_DEMAND" and r.recommended_models == []


# --- ABC ---------------------------------------------------------------------
def test_abc_classes_by_cumulative_value():
    rows = [
        {"product_id": 1, "units": 1000, "unit_cost": 100, "covered_days": 365},  # huge
        {"product_id": 2, "units": 100, "unit_cost": 100, "covered_days": 365},
        {"product_id": 3, "units": 10, "unit_cost": 100, "covered_days": 365},
        {"product_id": 4, "units": 1, "unit_cost": 100, "covered_days": 365},
    ]
    res = abc_classify(rows)
    classes = {i.product_id: i.abc_class for i in res.ranked}
    assert classes[1] == "A"  # dominates cumulative value
    assert classes[4] == "C"  # tail
    # Ranked in descending value, cumulative share monotonic increasing.
    shares = [i.cumulative_share for i in res.ranked]
    assert shares == sorted(shares)


def test_abc_short_history_excluded_with_confidence():
    rows = [
        {"product_id": 1, "units": 50, "unit_cost": 100, "covered_days": 365},
        {"product_id": 2, "units": 50, "unit_cost": 100, "covered_days": 5},  # short
    ]
    res = abc_classify(rows)
    assert [i.product_id for i in res.ranked] == [1]
    assert len(res.new_products) == 1
    np = res.new_products[0]
    assert np["product_id"] == 2 and np["status"] == "ABC_EVIDENCE_SHORT"
    assert np["annualisation_confidence"] == round(5 / ABC_MIN_COVERED_DAYS, 4)
