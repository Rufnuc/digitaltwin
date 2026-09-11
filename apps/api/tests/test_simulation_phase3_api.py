"""Phase 3 API: Monte Carlo / sensitivity / compare endpoints, backed by seed data."""
from __future__ import annotations

from app.seed.demo_data import seed


def test_monte_carlo_endpoint(client, auth_headers, db):
    seed(db)
    headers = auth_headers("ANALYST")
    r = client.post("/api/v1/simulations/monte-carlo", headers=headers, json={
        "name": "Price uncertainty",
        "parameters": {
            "distributions": {
                "price_pct": {"type": "normal", "mean": 5, "std": 4},
                "unit_cost_pct": {"type": "triangular", "low": 0, "mode": 3, "high": 8},
            }
        },
        "iterations": 1000,
        "target_metric": "net_profit",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "COMPLETED"
    assert body["model_name"] == "monte_carlo"
    mc = body["assumptions"]["monte_carlo"]
    assert 0.0 <= mc["probability_of_loss"] <= 1.0
    assert mc["iterations"] == 1000
    # Each metric result carries a percentile distribution.
    net = next(r for r in body["results"] if r["metric"] == "net_profit")
    assert "p5" in net["scenario"] and "p95" in net["scenario"]


def test_sensitivity_endpoint(client, auth_headers, db):
    seed(db)
    r = client.post("/api/v1/simulations/sensitivity", headers=auth_headers("ANALYST"), json={
        "parameters": {"price_change_percent": 0},
        "assumptions": {"price_elasticity": -0.8},
        "target_metric": "net_profit",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "ranking" in body and len(body["ranking"]) >= 1


def test_compare_endpoint(client, auth_headers, db):
    seed(db)
    r = client.post("/api/v1/simulations/compare", headers=auth_headers("ANALYST"), json={
        "scenarios": [
            {"name": "A +10%", "parameters": {"price_change_percent": 10},
             "assumptions": {"price_elasticity": -0.8}},
            {"name": "B hold", "parameters": {}},
        ]
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["best_by_net_profit"] in {"A +10%", "B hold"}
    assert len(body["scenarios"]) == 2


def test_analyst_required_for_montecarlo(client, auth_headers):
    r = client.post("/api/v1/simulations/monte-carlo", headers=auth_headers("STAFF"), json={
        "name": "x", "parameters": {"distributions": {}}, "iterations": 100})
    assert r.status_code == 403
