"""Deterministic simulation-engine tests (spec §2, §21, §46)."""
from __future__ import annotations

from app.services.analytics import BaselineEconomics
from app.services.simulation.base import ScenarioRequest, get_engine
from app.services.simulation.price_change import PriceChangeEngine


def _baseline() -> BaselineEconomics:
    # 1000 units @ $10 price, $6 cost -> rev 10000, cogs 6000, gp 4000, margin 0.4
    return BaselineEconomics(
        revenue=10000.0, cogs=6000.0, units=1000.0, avg_unit_price=10.0,
        avg_unit_cost=6.0, gross_profit=4000.0, gross_margin=0.4, order_count=100,
    )


def test_price_change_engine_is_registered():
    assert get_engine("price_change") is not None


def test_price_increase_with_zero_elasticity_is_pure_price_effect():
    engine = PriceChangeEngine()
    req = ScenarioRequest(scenario_type="price_change",
                          parameters={"price_change_percent": 10},
                          assumptions={"price_elasticity": 0.0})
    out = engine.run(req, _baseline())
    metrics = {r.metric: r for r in out.results}
    # +10% price, no demand response -> revenue 11000, units unchanged.
    assert metrics["revenue"].scenario["value"] == 11000.0
    assert metrics["units_sold"].scenario["value"] == 1000.0
    # gross profit = 11000 - 6000 = 5000
    assert metrics["gross_profit"].scenario["value"] == 5000.0


def test_price_increase_with_elasticity_reduces_units():
    engine = PriceChangeEngine()
    req = ScenarioRequest(scenario_type="price_change",
                          parameters={"price_change_percent": 10},
                          assumptions={"price_elasticity": -0.8})
    out = engine.run(req, _baseline())
    metrics = {r.metric: r for r in out.results}
    # demand change = -0.8 * 10 = -8% -> 920 units
    assert metrics["units_sold"].scenario["value"] == 920.0
    # revenue = 920 * 11 = 10120
    assert metrics["revenue"].scenario["value"] == 10120.0
    assert out.assumptions["price_elasticity"] == -0.8


def test_empty_baseline_emits_warning():
    engine = PriceChangeEngine()
    req = ScenarioRequest(scenario_type="price_change",
                          parameters={"price_change_percent": 5})
    empty = BaselineEconomics(0, 0, 0, 0, 0, 0, 0, 0)
    out = engine.run(req, empty)
    assert out.warnings  # insufficient-data warning, not a fabricated result
