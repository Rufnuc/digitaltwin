"""Plain-language simulation for non-technical owners.

`auto_explore` runs a preset grid of "what ifs" in every direction (prices up/down,
demand up/down, supplier cost up/down, plus a couple of combinations) against the
current business, ranks them by profit and explains each in one sentence — one
click, no jargon. `manual_scenario` runs a single owner-chosen change. Both persist
a timestamped SimulationRun so the history can be reopened later.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.simulation import SimulationRun
from app.services.analytics import baseline_economics
from app.services.simulation.compare import compare_scenarios

_ELASTICITY = -0.8  # default price elasticity assumption

# (label, parameters) — single-lever moves plus two realistic combinations.
_GRID: list[tuple[str, dict]] = [
    ("Raise prices 5%", {"price_change_percent": 5}),
    ("Raise prices 10%", {"price_change_percent": 10}),
    ("Raise prices 15%", {"price_change_percent": 15}),
    ("Cut prices 5%", {"price_change_percent": -5}),
    ("Cut prices 10%", {"price_change_percent": -10}),
    ("Sell 10% more", {"demand_change_percent": 10}),
    ("Sell 20% more", {"demand_change_percent": 20}),
    ("Sell 10% less", {"demand_change_percent": -10}),
    ("Sell 20% less", {"demand_change_percent": -20}),
    ("Supplier cost up 5%", {"unit_cost_change_percent": 5}),
    ("Supplier cost up 10%", {"unit_cost_change_percent": 10}),
    ("Supplier cost down 5%", {"unit_cost_change_percent": -5}),
    ("Raise prices 10% (lose 5% sales)",
     {"price_change_percent": 10, "demand_change_percent": -5}),
    ("Cut prices 10% (win 15% sales)",
     {"price_change_percent": -10, "demand_change_percent": 15}),
]

_EPS = 1.0  # naira: below this a profit change reads as "about the same"


def _verdict(profit_delta: float) -> str:
    if profit_delta > _EPS:
        return "better"
    if profit_delta < -_EPS:
        return "worse"
    return "about the same"


def _explain(name: str, base_profit: float, values: dict, deltas: dict) -> dict:
    pd = deltas["net_profit"]
    pct = (pd / base_profit * 100) if base_profit else 0.0
    verdict = _verdict(pd)
    return {
        "name": name,
        "net_profit": values["net_profit"],
        "net_profit_delta": round(pd, 2),
        "net_profit_pct": round(pct, 1),
        "revenue": values["revenue"],
        "revenue_delta": round(deltas["revenue"], 2),
        "verdict": verdict,
    }


def _persist(db: Session, name: str, scenario_type: str, payload: dict,
             user_id: int | None) -> int:
    run = SimulationRun(
        name=name, scenario_type=scenario_type, parameters={}, assumptions={},
        horizon_months=12, iterations=1, model_name="plain_language", model_version="1.0.0",
        status="COMPLETED", result_json=payload, created_by_id=user_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run.id


def auto_explore(db: Session, user_id: int | None = None,
                 elasticity: float = _ELASTICITY) -> dict:
    """Run every preset 'what if' and rank them by profit, in plain English."""
    baseline = baseline_economics(db)
    scenarios = [
        {"name": n, "parameters": p, "assumptions": {"price_elasticity": elasticity}}
        for n, p in _GRID
    ]
    comp = compare_scenarios(baseline, scenarios)
    base_profit = comp["baseline"]["net_profit"]
    by_name = {r["name"]: r for r in comp["scenarios"]}
    outcomes = [
        _explain(n, base_profit, by_name[n]["values"], by_name[n]["deltas"])
        for n, _ in _GRID
    ]
    outcomes.sort(key=lambda o: o["net_profit_delta"], reverse=True)

    payload = {
        "kind": "auto_explore",
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "baseline": {"net_profit": base_profit, "revenue": comp["baseline"]["revenue"]},
        "best": outcomes[0]["name"] if outcomes else None,
        "worst": outcomes[-1]["name"] if outcomes else None,
        "outcomes": outcomes,
        "assumptions": {"price_elasticity": elasticity},
        "provenance": "MODEL_OUTPUT",
    }
    payload["run_id"] = _persist(
        db, f"Auto explore {payload['as_of'][:16]}", "auto_explore", payload, user_id)
    return payload


def manual_scenario(db: Session, *, price_change_percent: float = 0.0,
                    demand_change_percent: float = 0.0,
                    unit_cost_change_percent: float = 0.0,
                    elasticity: float = _ELASTICITY, user_id: int | None = None) -> dict:
    """Run one owner-chosen change against the current business."""
    baseline = baseline_economics(db)
    params = {
        "price_change_percent": price_change_percent,
        "demand_change_percent": demand_change_percent,
        "unit_cost_change_percent": unit_cost_change_percent,
    }
    comp = compare_scenarios(baseline, [
        {"name": "Your scenario", "parameters": params,
         "assumptions": {"price_elasticity": elasticity}}
    ])
    base_profit = comp["baseline"]["net_profit"]
    row = comp["scenarios"][0]
    outcome = _explain("Your scenario", base_profit, row["values"], row["deltas"])
    payload = {
        "kind": "manual",
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "inputs": params,
        "baseline": {"net_profit": base_profit, "revenue": comp["baseline"]["revenue"],
                     "gross_margin": comp["baseline"].get("gross_margin")},
        "result": {**outcome, "gross_margin": row["values"].get("gross_margin")},
        "assumptions": {"price_elasticity": elasticity},
        "provenance": "MODEL_OUTPUT",
    }
    payload["run_id"] = _persist(db, f"Manual scenario {payload['as_of'][:16]}",
                                 "manual", payload, user_id)
    return payload
