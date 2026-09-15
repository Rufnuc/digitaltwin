"""Quant Phase 1 — lead-time statistics and their effect on safety stock."""
from __future__ import annotations

from app.services.quant import leadtime as lt
from app.services.quant import reorder as ro

from .golden_utils import assert_golden


def test_empirical_stats_and_risk():
    # Mostly ~10 days, with occasional long tails.
    samples = [10, 10, 11, 9, 10, 12, 20, 10, 11, 10]
    s = lt.lead_time_stats(samples)
    assert s["status"] == "OK" and s["source"] == "EMPIRICAL" and s["n"] == 10
    assert s["std_days"] > 0
    assert s["p95_days"] >= s["p50_days"]
    # lead_time_risk = clamp((p95 - p50)/max(p50,1), 0, 1)
    assert 0.0 <= s["lead_time_risk"] <= 1.0


def test_point_fallback_when_too_few_samples():
    s = lt.lead_time_stats([12], point_estimate=14.0)
    assert s["source"] == "ESTIMATED" and s["std_days"] == 0.0
    assert s["mean_days"] == 14.0 and s["lead_time_risk"] == 0.0
    assert "LEAD_TIME_POINT_ESTIMATE" in s.get("warnings", [])


def test_unknown_when_no_evidence_and_no_estimate():
    s = lt.lead_time_stats([], point_estimate=None)
    assert s["status"] == "UNKNOWN" and s["mean_days"] is None


def test_constant_lead_time_has_zero_std():
    s = lt.lead_time_stats([7, 7, 7, 7])
    assert s["std_days"] == 0.0 and s["p50_days"] == 7.0 and s["lead_time_risk"] == 0.0


def _rec(**kw):
    base = dict(
        weekly_mean=70.0, weekly_std=14.0, inventory_position=0.0,
        mean_lead_time_days=14.0, review_period_days=7, service_level=0.95,
        unit_cost=100.0, wape=0.3, validation_status="OK",
    )
    base.update(kw)
    return ro.reorder_recommendation(**base)


def test_lead_time_variability_raises_safety_stock():
    calm = _rec(std_lead_time_days=0.0)
    variable = _rec(std_lead_time_days=5.0)
    assert variable["safety_stock"] > calm["safety_stock"]
    # The lead-time component is zero when there is no lead-time variability.
    assert calm["sigma_lead_time_component"] == 0.0
    assert variable["sigma_lead_time_component"] > 0.0
    # sigma_over combines the two components in quadrature.
    combined = (variable["sigma_demand_component"] ** 2
                + variable["sigma_lead_time_component"] ** 2) ** 0.5
    assert abs(variable["sigma_over_horizon"] - round(combined, 4)) <= 1e-3


def test_reorder_periodic_review_golden():
    rec = _rec(std_lead_time_days=3.0)
    # Drop the free-text provenance dict; keep the numeric contract stable.
    rec.pop("provenance", None)
    assert_golden("reorder_periodic_review", rec)
