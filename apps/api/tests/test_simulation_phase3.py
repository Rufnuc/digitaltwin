"""Phase 3: projection model, general engines, Monte Carlo, sensitivity, compare."""
from __future__ import annotations

import pytest

from app.services.analytics import BaselineEconomics
from app.services.simulation.base import get_engine
from app.services.simulation.compare import compare_scenarios
from app.services.simulation.model import Levers, project
from app.services.simulation.montecarlo import run_monte_carlo
from app.services.simulation.sensitivity import tornado

# 1000 units @ $10 (cost $6), $1000 opex -> rev 10000, cogs 6000, gross 4000, net 3000.
BASE = BaselineEconomics(
    revenue=10000.0, cogs=6000.0, units=1000.0, avg_unit_price=10.0, avg_unit_cost=6.0,
    gross_profit=4000.0, gross_margin=0.4, order_count=100, operating_expenses=1000.0,
)


def test_projection_identity():
    p = project(BASE, Levers())
    assert p.revenue == 10000.0
    assert p.gross_profit == 4000.0
    assert p.net_profit == 3000.0  # gross - opex


def test_projection_price_increase_no_elasticity():
    p = project(BASE, Levers(price_pct=10, elasticity=0))
    assert p.revenue == 11000.0
    assert p.net_profit == 4000.0  # +1000 straight to the bottom line


def test_supplier_cost_increase_hits_margin():
    p = project(BASE, Levers(unit_cost_pct=10))  # cost 6 -> 6.6
    assert p.cogs == pytest.approx(6600.0)
    assert p.gross_profit == pytest.approx(3400.0)
    assert p.net_profit == pytest.approx(2400.0)


def test_general_engines_registered():
    for st in ("demand_change", "supplier_cost_change", "cost_change"):
        assert get_engine(st) is not None, st


def test_monte_carlo_fixed_distributions_are_deterministic():
    # All variables fixed -> every draw identical -> zero spread, prob_loss 0.
    dists = {"price_pct": {"type": "fixed", "value": 10}}
    mc = run_monte_carlo(BASE, dists, iterations=500)
    net = mc["distributions_by_metric"]["net_profit"]
    assert net["p5"] == net["p95"] == net["mean"] == 4000.0
    assert mc["probability_of_loss"] == 0.0


def test_monte_carlo_reproducible_and_bounded():
    dists = {
        "price_pct": {"type": "normal", "mean": 0, "std": 5},
        "unit_cost_pct": {"type": "normal", "mean": 5, "std": 5},
    }
    a = run_monte_carlo(BASE, dists, iterations=2000, seed=7)
    b = run_monte_carlo(BASE, dists, iterations=2000, seed=7)
    assert a["probability_of_loss"] == b["probability_of_loss"]  # seeded => reproducible
    assert 0.0 <= a["probability_of_loss"] <= 1.0
    net = a["distributions_by_metric"]["net_profit"]
    assert net["p5"] <= net["p50"] <= net["p95"]  # ordered percentiles
    # Sensitivity ranks the varying inputs by correlation with the target.
    vars_ranked = [s["variable"] for s in a["sensitivity"]]
    assert set(vars_ranked) == {"price_pct", "unit_cost_pct"}


def test_tornado_ranks_by_swing():
    variations = {
        "price_pct": {"low": -10, "high": 10},
        "unit_cost_pct": {"low": -10, "high": 10},
    }
    t = tornado(BASE, {}, {}, variations, target_metric="net_profit")
    assert t["base_value"] == 3000.0
    assert [r["variable"] for r in t["ranking"]]  # ranked, non-empty
    # swings are non-negative and sorted descending
    swings = [r["swing"] for r in t["ranking"]]
    assert swings == sorted(swings, reverse=True)


def test_compare_ranks_best_by_net_profit():
    result = compare_scenarios(
        BASE,
        [
            {"name": "Hold", "parameters": {}},
            {"name": "Raise 10%", "parameters": {"price_change_percent": 10},
             "assumptions": {"price_elasticity": -0.5}},
            {"name": "Cut 5%", "parameters": {"price_change_percent": -5},
             "assumptions": {"price_elasticity": -0.5}},
        ],
    )
    assert result["baseline"]["net_profit"] == 3000.0
    assert len(result["scenarios"]) == 3
    assert result["best_by_net_profit"] in {"Hold", "Raise 10%", "Cut 5%"}
