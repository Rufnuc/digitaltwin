"""Quant golden files for the deterministic engine (spec §17 required goldens).

These lock the exact outputs of the pure forecasting/classification/EOQ engines on
fixed fixtures. Regenerate deliberately with UPDATE_GOLDEN=1 after reviewing a diff.
"""
from __future__ import annotations

from dataclasses import asdict

from app.services.quant import classification as cls
from app.services.quant import forecast as fc
from app.services.quant import forecast_models as fm
from app.services.quant import reorder as ro

from .golden_utils import assert_golden

# A fixed intermittent weekly series and a smooth one.
INTERMITTENT = [0, 0, 4, 0, 0, 3, 0, 0, 5, 0, 2, 0, 0, 6, 0, 0, 3, 0, 0, 4]
SMOOTH = [12, 14, 11, 13, 12, 15, 12, 13, 11, 14, 12, 13, 12, 14, 13, 12]


def _fit(m: fm.ModelFit) -> dict:
    d = asdict(m)
    d["point_rate"] = round(float(d["point_rate"]), 8)
    d["params"] = {k: (round(v, 8) if isinstance(v, float) else v)
                   for k, v in d["params"].items()}
    return d


def test_golden_croston():
    assert_golden("croston_model", _fit(fm.croston(INTERMITTENT)))


def test_golden_sba():
    assert_golden("sba_model", _fit(fm.sba(INTERMITTENT)))


def test_golden_tsb():
    assert_golden("tsb_forecast", _fit(fm.tsb(INTERMITTENT)))


def test_golden_croston_sba_forecast_envelope():
    r = fc.forecast(INTERMITTENT, "INTERMITTENT", horizon=4, seed=42)
    assert_golden("croston_sba_forecast", r)


def test_golden_smooth_forecast_envelope():
    r = fc.forecast(SMOOTH, "SMOOTH", horizon=4, seed=42)
    assert_golden("forecast_api_envelope", r)


def test_golden_abc_classification():
    rows = [
        {"product_id": 1, "annual_demand_value": 100000.0, "covered_days": 200},
        {"product_id": 2, "annual_demand_value": 15000.0, "covered_days": 200},
        {"product_id": 3, "annual_demand_value": 4000.0, "covered_days": 200},
        {"product_id": 4, "annual_demand_value": 900.0, "covered_days": 200},
        {"product_id": 5, "annual_demand_value": 50.0, "covered_days": 10},  # short history
    ]
    assert_golden("abc_classification", cls.classify_abc(rows))


def test_golden_eoq_fallback_and_valid():
    fallback = ro.eoq(annual_demand_units=520.0, ordering_cost=None, unit_cost=100.0)
    valid = ro.eoq(annual_demand_units=520.0, ordering_cost=2500.0, unit_cost=100.0,
                   moq=1.0, order_multiple=10.0)
    assert_golden("eoq_fallback", {"fallback": fallback, "valid": valid})
