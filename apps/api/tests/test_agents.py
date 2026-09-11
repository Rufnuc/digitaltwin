"""Phase 8: multi-agent digital-twin simulation."""
from __future__ import annotations

from app.seed.demo_data import seed
from app.services.agents import simulation


def _assumptions(**over):
    base = dict(simulation.DEFAULT_ASSUMPTIONS)
    base.update(over)
    return base


def test_calibrates_from_real_customers(db):
    seed(db)
    world = simulation.calibrate(db, simulation.DEFAULT_ASSUMPTIONS)
    assert world is not None
    assert world.n_customers > 0
    assert len(world.purchase_prob) == world.n_customers
    assert world.base_price > 0 and world.base_unit_cost > 0
    assert world.calibration["customers_modelled"] == world.n_customers


def test_no_customers_returns_none(db):
    # No seed -> no customer history -> cannot calibrate.
    assert simulation.calibrate(db, simulation.DEFAULT_ASSUMPTIONS) is None
    assert simulation.simulate(db, {}, 12, 100, None) is None


def test_run_is_reproducible(db):
    seed(db)
    r1 = simulation.simulate(db, {"price_change_percent": 0}, 12, 200, None, seed=7)
    r2 = simulation.simulate(db, {"price_change_percent": 0}, 12, 200, None, seed=7)
    assert r1["cumulative_net_profit"]["mean"] == r2["cumulative_net_profit"]["mean"]
    assert 0.0 <= r1["probability_of_cumulative_loss"] <= 1.0
    # percentiles are ordered
    c = r1["cumulative_net_profit"]
    assert c["p5"] <= c["p50"] <= c["p95"]


def test_no_churn_keeps_all_customers(db):
    seed(db)
    r = simulation.simulate(db, {}, 12, 100, _assumptions(base_monthly_churn=0.0), seed=1)
    assert r["expected_active_customers_end"] == r["customers_start"]


def test_churn_reduces_customers(db):
    seed(db)
    r = simulation.simulate(db, {}, 12, 200, _assumptions(base_monthly_churn=0.1), seed=1)
    assert r["expected_active_customers_end"] < r["customers_start"]


def test_price_increase_with_zero_elasticity_raises_profit(db):
    seed(db)
    a = _assumptions(price_elasticity=0.0, base_monthly_churn=0.0, macro_demand_drag=0.0)
    hold = simulation.simulate(db, {"price_change_percent": 0}, 12, 200, a, seed=3)
    up = simulation.simulate(db, {"price_change_percent": 10}, 12, 200, a, seed=3)
    assert up["cumulative_net_profit"]["mean"] > hold["cumulative_net_profit"]["mean"]


def test_compare_policies_picks_best(db):
    seed(db)
    res = simulation.compare_policies(
        db,
        [{"name": "Hold", "price_change_percent": 0},
         {"name": "Raise 10%", "price_change_percent": 10}],
        12, 200, _assumptions(price_elasticity=0.0, base_monthly_churn=0.0, macro_demand_drag=0.0),
    )
    assert res["best_by_expected_profit"] == "Raise 10%"
    assert len(res["strategies"]) == 2


def test_agents_api(client, auth_headers, db):
    seed(db)
    roster = client.get("/api/v1/agents/roster", headers=auth_headers("VIEWER"))
    assert roster.status_code == 200 and len(roster.json()["agents"]) == 4

    sim = client.post("/api/v1/agents/simulate", headers=auth_headers("ANALYST"),
                      json={"policy": {"price_change_percent": 5}, "iterations": 150})
    assert sim.status_code == 200, sim.text
    body = sim.json()
    assert body["provenance"]["outcome"] == "FORECAST"
    assert len(body["monthly_net_profit_path"]) == 12

    # Staff cannot run agent simulations.
    assert client.post("/api/v1/agents/simulate", headers=auth_headers("STAFF"),
                       json={}).status_code == 403
