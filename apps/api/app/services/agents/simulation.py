"""Multi-agent digital-twin simulation (spec §33, §34, Phase 8).

Simulated CUSTOMER / SUPPLIER / COMPETITOR / MARKET agents interact month by month
in a stochastic (Monte Carlo) forward simulation. Agents are **calibrated from
real historical data** (per-customer cadence, order size, churn risk; unit
economics; latest inflation) and constrained by **explicit behavioural
assumptions**. Outputs are FORECASTS with uncertainty — simulated behaviour is
never presented as real-world fact.

Provenance of the pieces:
  REAL OBSERVATION  — calibration inputs (customer metrics, baseline, macro)
  ASSUMPTION        — behavioural parameters (elasticity, churn, competitor, drift)
  SIMULATED BEHAVIOUR — the agents' monthly decisions
  FORECAST          — the distribution of outcomes
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.events import EconomicData
from app.services.analytics import baseline_economics
from app.services.bi.customers import customer_metrics

DEFAULT_ASSUMPTIONS = {
    "price_elasticity": -0.8,      # demand response to our price change
    "base_monthly_churn": 0.02,    # monthly churn hazard for a normal customer
    "churn_risk_multiplier": 3.0,  # ×hazard for customers already flagged at risk
    "competitor_price_index": 1.0,  # competitor price ÷ our baseline price
    "competitor_sensitivity": 0.5,  # demand lost per unit of price premium over competitor
    "macro_demand_drag": 0.3,      # fraction of inflation that dampens real demand
    "fx_annual_depreciation": 0.0,  # extra annual cost drift from FX (assumption)
}


@dataclass
class AgentWorld:
    n_customers: int
    purchase_prob: np.ndarray        # monthly purchase probability per customer
    units_per_order: np.ndarray
    churn_hazard: np.ndarray
    base_price: float
    base_unit_cost: float
    monthly_opex: float
    inflation_annual: float          # fraction, e.g. 0.23
    calibration: dict = field(default_factory=dict)


def _latest_inflation(db: Session) -> float | None:
    row = db.scalar(
        select(EconomicData)
        .where(EconomicData.indicator == "inflation_cpi_yoy")
        .order_by(EconomicData.period.desc())
    )
    return float(row.value) / 100.0 if row else None


def calibrate(db: Session, assumptions: dict) -> AgentWorld | None:
    metrics = [m for m in customer_metrics(db) if m.orders > 0]
    if not metrics:
        return None

    probs, upos, hazards = [], [], []
    base_churn = float(assumptions["base_monthly_churn"])
    risk_mult = float(assumptions["churn_risk_multiplier"])
    for m in metrics:
        if m.avg_interval_days and m.avg_interval_days > 0:
            prob = min(1.0, 30.0 / m.avg_interval_days)
        else:
            prob = min(1.0, m.orders / 24.0)
        probs.append(max(prob, 0.01))
        upos.append((m.units / m.orders) if m.orders else 0.0)
        hazards.append(base_churn * (risk_mult if m.churn_risk else 1.0))

    econ = baseline_economics(db)
    inflation = _latest_inflation(db)
    if inflation is None:
        inflation = 0.20  # assumption when no market data has been ingested
    return AgentWorld(
        n_customers=len(metrics),
        purchase_prob=np.array(probs),
        units_per_order=np.array(upos),
        churn_hazard=np.array(hazards),
        base_price=econ.avg_unit_price,
        base_unit_cost=econ.avg_unit_cost,
        monthly_opex=econ.operating_expenses / 24.0,   # 24-month window
        inflation_annual=inflation,
        calibration={
            "customers_modelled": len(metrics),
            "avg_unit_price": round(econ.avg_unit_price, 2),
            "avg_unit_cost": round(econ.avg_unit_cost, 2),
            "monthly_operating_expenses": round(econ.operating_expenses / 24.0, 2),
            "inflation_annual_pct": round(inflation * 100, 2),
        },
    )


def _percentiles(arr: np.ndarray) -> dict:
    return {
        "p5": round(float(np.percentile(arr, 5)), 2),
        "p50": round(float(np.percentile(arr, 50)), 2),
        "p95": round(float(np.percentile(arr, 95)), 2),
        "mean": round(float(arr.mean()), 2),
    }


def run(
    world: AgentWorld,
    policy: dict,
    horizon_months: int = 12,
    iterations: int = 400,
    assumptions: dict | None = None,
    seed: int = 42,
) -> dict:
    a = {**DEFAULT_ASSUMPTIONS, **(assumptions or {})}
    iterations = max(50, min(int(iterations), 5000))
    horizon = max(1, min(int(horizon_months), 60))
    rng = np.random.default_rng(seed)
    n = world.n_customers

    price_change = float(policy.get("price_change_percent", 0.0))
    opex_delta = float(policy.get("monthly_opex_delta", 0.0))

    # MARKET + policy-derived monthly multipliers (SIMULATED BEHAVIOUR / ASSUMPTION).
    our_price = world.base_price * (1 + price_change / 100.0)
    competitor_price = world.base_price * float(a["competitor_price_index"])
    price_response = max(0.0, 1 + float(a["price_elasticity"]) * price_change / 100.0)
    premium = max(0.0, our_price / competitor_price - 1.0) if competitor_price else 0.0
    competitor_effect = max(0.3, 1 - float(a["competitor_sensitivity"]) * premium)
    macro_demand = max(0.3, 1 - float(a["macro_demand_drag"]) * world.inflation_annual)
    demand_mult = price_response * competitor_effect * macro_demand
    monthly_cost_drift = world.inflation_annual / 12.0 + float(a["fx_annual_depreciation"]) / 12.0

    cumulative = np.zeros(iterations)
    active_end = np.zeros(iterations)
    monthly_paths = np.zeros((iterations, horizon))

    for it in range(iterations):
        active = np.ones(n, dtype=bool)
        cost_index = 1.0
        for month in range(horizon):
            cost_index *= (1 + monthly_cost_drift)
            buy = active & (rng.random(n) < world.purchase_prob * demand_mult)
            units = float((buy * world.units_per_order).sum())
            revenue = units * our_price
            cogs = units * world.base_unit_cost * cost_index
            opex = world.monthly_opex * cost_index + opex_delta
            net = revenue - cogs - opex
            monthly_paths[it, month] = net
            cumulative[it] += net
            # churn among currently-active customers (SIMULATED BEHAVIOUR)
            churn = active & (rng.random(n) < world.churn_hazard)
            active = active & ~churn
        active_end[it] = int(active.sum())

    path = [
        {"month": m + 1, **_percentiles(monthly_paths[:, m])} for m in range(horizon)
    ]
    return {
        "policy": {"price_change_percent": price_change, "monthly_opex_delta": opex_delta},
        "horizon_months": horizon,
        "iterations": iterations,
        "cumulative_net_profit": _percentiles(cumulative),
        "monthly_net_profit_path": path,
        "probability_of_cumulative_loss": round(float((cumulative < 0).mean()), 4),
        "expected_active_customers_end": round(float(active_end.mean()), 1),
        "customers_start": n,
        "assumptions": a,
        "calibration": world.calibration,
        "provenance": {
            "calibration": "REAL",
            "behaviour": "ASSUMPTION",
            "outcome": "FORECAST",
        },
    }


def simulate(db: Session, policy: dict, horizon_months: int, iterations: int,
             assumptions: dict | None, seed: int = 42) -> dict | None:
    world = calibrate(db, {**DEFAULT_ASSUMPTIONS, **(assumptions or {})})
    if world is None:
        return None
    return run(world, policy, horizon_months, iterations, assumptions, seed)


def compare_policies(db: Session, strategies: list[dict], horizon_months: int,
                     iterations: int, assumptions: dict | None) -> dict | None:
    world = calibrate(db, {**DEFAULT_ASSUMPTIONS, **(assumptions or {})})
    if world is None:
        return None
    rows = []
    for i, s in enumerate(strategies):
        res = run(world, s, horizon_months, iterations, assumptions, seed=42 + i)
        rows.append({
            "name": s.get("name", f"strategy {i + 1}"),
            "price_change_percent": float(s.get("price_change_percent", 0.0)),
            "expected_cumulative_net_profit": res["cumulative_net_profit"]["mean"],
            "p5": res["cumulative_net_profit"]["p5"],
            "p95": res["cumulative_net_profit"]["p95"],
            "probability_of_loss": res["probability_of_cumulative_loss"],
            "expected_active_customers_end": res["expected_active_customers_end"],
        })
    ranked = sorted(rows, key=lambda r: r["expected_cumulative_net_profit"], reverse=True)
    return {
        "strategies": rows,
        "best_by_expected_profit": ranked[0]["name"] if ranked else None,
        "calibration": world.calibration,
        "provenance": {"calibration": "REAL", "behaviour": "ASSUMPTION", "outcome": "FORECAST"},
    }


AGENT_ROSTER = [
    {"agent": "Customer", "count": "per real customer",
     "behaviour": "Buys on their own historical cadence; may churn; responds to our price "
                  "(elasticity) and to the competitor's price.",
     "calibrated_from": "real per-customer frequency, order size, churn risk"},
    {"agent": "Supplier", "count": "aggregate",
     "behaviour": "Unit cost drifts up with inflation (and optional FX depreciation).",
     "calibrated_from": "baseline unit cost + latest real inflation"},
    {"agent": "Competitor", "count": "1",
     "behaviour": "Prices relative to our baseline; a price premium on our side loses demand.",
     "calibrated_from": "assumption (competitor_price_index)"},
    {"agent": "Market", "count": "1",
     "behaviour": "Macro conditions dampen real demand and push costs up.",
     "calibrated_from": "latest real inflation (World Bank)"},
]
