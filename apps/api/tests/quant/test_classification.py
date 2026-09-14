"""Quant Phase 1 — demand series, ADI/CV² pattern, and ABC classification."""
from __future__ import annotations

from datetime import date

from app.services.quant import classification as cls
from app.services.quant.demand import DemandEvent, nonzero_stats, weekly_buckets


def test_weekly_buckets_align_and_fill_zeros():
    # Two sales three weeks apart -> a 3-bucket series with a zero middle week.
    events = [DemandEvent(date(2026, 1, 5), 4), DemandEvent(date(2026, 1, 19), 6)]
    buckets = weekly_buckets(events, as_of=date(2026, 1, 19))
    assert [b["units"] for b in buckets] == [4.0, 0.0, 6.0]
    assert buckets[0]["week_start"] == "2026-01-05"  # Monday of week 1


def test_weekly_buckets_sum_within_week():
    events = [DemandEvent(date(2026, 1, 6), 2), DemandEvent(date(2026, 1, 8), 3)]
    buckets = weekly_buckets(events, as_of=date(2026, 1, 8))
    assert [b["units"] for b in buckets] == [5.0]


def test_pattern_smooth():
    # Frequent, steady demand -> SMOOTH, low ADI, low CV².
    r = cls.classify_pattern([5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6])
    assert r["pattern"] == "SMOOTH"
    assert r["adi"] == 1.0
    assert r["cv_squared"] < cls.CV2_CUTOFF
    assert "ses" in r["eligible_models"]


def test_pattern_intermittent():
    # Sparse but equal-size demand -> ADI high, CV² low.
    r = cls.classify_pattern([0, 0, 3, 0, 0, 3, 0, 0, 3, 0, 0, 3])
    assert r["adi"] > cls.ADI_CUTOFF
    assert r["cv_squared"] < cls.CV2_CUTOFF
    assert r["pattern"] == "INTERMITTENT"
    assert "croston" in r["eligible_models"]


def test_pattern_lumpy():
    # Sparse AND highly variable sizes -> LUMPY.
    r = cls.classify_pattern([0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 20])
    assert r["adi"] > cls.ADI_CUTOFF
    assert r["cv_squared"] >= cls.CV2_CUTOFF
    assert r["pattern"] == "LUMPY"


def test_pattern_no_evidence():
    r = cls.classify_pattern([0, 0, 0])
    assert r["pattern"] == "NO_EVIDENCE"
    assert "NO_SALES_HISTORY" in r["warnings"]


def test_nonzero_stats():
    s = nonzero_stats([0, 4, 0, 6, 0, 5])
    assert s["nonzero_periods"] == 3
    assert s["nonzero_mean"] == 5.0


def test_abc_ranks_and_short_history_gate():
    products = [
        {"product_id": 1, "annual_demand_value": 800, "covered_days": 365},
        {"product_id": 2, "annual_demand_value": 150, "covered_days": 365},
        {"product_id": 3, "annual_demand_value": 50, "covered_days": 365},
        {"product_id": 4, "annual_demand_value": 999, "covered_days": 5},  # short history
    ]
    r = cls.classify_abc(products)
    ids = [i["product_id"] for i in r["items"]]
    assert ids == [1, 2, 3]  # ranked by value desc; product 4 excluded
    assert r["items"][0]["abc_class"] == "A"  # 80% of 1000 value
    # short-history product held out with a confidence-adjusted value.
    new = r["new_products"][0]
    assert new["product_id"] == 4 and new["status"] == "ABC_EVIDENCE_SHORT"
    assert new["annualisation_confidence"] == round(5 / 30, 4)
