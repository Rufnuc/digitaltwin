"""End-to-end simulation via the API, backed by seeded data (spec §35)."""
from __future__ import annotations

from app.seed.demo_data import seed


def test_full_simulation_flow(client, auth_headers, db):
    seed(db)
    headers = auth_headers("ANALYST")

    create = client.post("/api/v1/simulations", headers=headers, json={
        "name": "Raise prices 10%",
        "scenario_type": "price_change",
        "parameters": {"price_change_percent": 10},
        "assumptions": {"price_elasticity": -0.8},
        "horizon_months": 12,
    })
    assert create.status_code == 201, create.text
    run_id = create.json()["id"]
    assert create.json()["status"] == "PENDING"

    run = client.post(f"/api/v1/simulations/{run_id}/run", headers=headers)
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "COMPLETED"
    assert body["model_name"] == "price_change_deterministic"
    metrics = {r["metric"] for r in body["results"]}
    assert {"revenue", "gross_profit", "gross_margin", "units_sold"} <= metrics
    # Reproducibility metadata stored.
    assert body["input_data_version"] is not None
    # Elasticity assumption surfaced, never hidden.
    assert body["assumptions"]["price_elasticity"] == -0.8


def test_analyst_required_to_create_simulation(client, auth_headers):
    r = client.post("/api/v1/simulations", headers=auth_headers("STAFF"), json={
        "name": "x", "scenario_type": "price_change", "parameters": {}})
    assert r.status_code == 403
