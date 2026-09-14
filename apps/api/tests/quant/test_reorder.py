"""Quant Phase 1 — reorder policies, safety stock, EOQ."""
from __future__ import annotations

import math

from app.services.quant import reorder as ro


def test_norm_ppf_known_quantiles():
    assert abs(ro.norm_ppf(0.5)) < 1e-6
    assert abs(ro.norm_ppf(0.975) - 1.959964) < 1e-3
    assert abs(ro.norm_ppf(0.95) - 1.644854) < 1e-3


def test_protection_horizon():
    # periodic review 7 + ceil(lead 3.2) = 7 + 4 = 11
    assert ro.protection_horizon_days(3.2, 7) == 11
    assert ro.protection_horizon_days(3.2, 7, continuous=True) == 4


def test_safety_stock_scales_with_service_level():
    ss90 = ro.safety_stock(10, 0.90)
    ss99 = ro.safety_stock(10, 0.99)
    assert ss99 > ss90 > 0


def test_eoq_formula_and_fallback():
    # D=1000, K=50, unit_cost=10, h=2.5 -> EOQ = sqrt(2*1000*50/2.5) = 200
    r = ro.eoq(1000, ordering_cost=50, unit_cost=10)
    assert r["status"] == "OK"
    assert abs(r["eoq_raw"] - 200.0) < 1e-6
    # missing ordering cost -> unavailable
    assert ro.eoq(1000, ordering_cost=None, unit_cost=10)["status"] == "EOQ_UNAVAILABLE"


def test_eoq_rounds_up_to_multiple():
    r = ro.eoq(1000, ordering_cost=50, unit_cost=10, order_multiple=25)
    assert r["eoq_constrained"] == 200.0  # already a multiple
    r2 = ro.eoq(1000, ordering_cost=53, unit_cost=10, order_multiple=25)
    assert r2["eoq_constrained"] % 25 == 0
    assert r2["eoq_constrained"] >= r2["eoq_raw"]


def test_reorder_recommendation_orders_when_below_target():
    r = ro.reorder_recommendation(
        weekly_mean=14, weekly_std=7, inventory_position=5,
        mean_lead_time_days=7, review_period_days=7, service_level=0.95, unit_cost=100,
    )
    assert r["policy"] == "ORDER_UP_TO"
    assert r["recommended_order_quantity"] > 0
    assert r["safety_stock"] > 0
    assert r["order_up_to_level"] > r["expected_demand_over_horizon"]
    # daily mean 2 * horizon(14) = 28 expected demand
    assert abs(r["expected_demand_over_horizon"] - 28.0) < 1e-6
    assert r["recommendation_status"] == "READY"


def test_reorder_quality_gate_suppresses_uncertain_forecast():
    r = ro.reorder_recommendation(
        weekly_mean=10, weekly_std=5, inventory_position=0,
        mean_lead_time_days=7, uncertainty_ratio=3.0,
    )
    assert r["recommendation_status"] == "REVIEW_REQUIRED"
    assert "FORECAST_UNRELIABLE" in r["warnings"]


def test_reorder_no_demand_signal():
    r = ro.reorder_recommendation(
        weekly_mean=0, weekly_std=0, inventory_position=10, mean_lead_time_days=5,
    )
    assert r["recommendation_status"] == "REVIEW_REQUIRED"
    assert r["recommended_order_quantity"] == 0
    assert math.isclose(r["expected_demand_over_horizon"], 0.0)
