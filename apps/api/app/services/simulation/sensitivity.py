"""Deterministic sensitivity (tornado) analysis (spec §22).

Answers "what matters most?" — vary each lever between a low and high bound, one
at a time, and rank levers by the swing they produce in a target metric.
"""
from __future__ import annotations

from dataclasses import replace

from app.services.analytics import BaselineEconomics
from app.services.simulation.model import levers_from_params, project

_LEVER_FIELDS = ("price_pct", "demand_pct", "unit_cost_pct", "fixed_opex_delta", "elasticity")


def tornado(
    baseline: BaselineEconomics,
    parameters: dict,
    assumptions: dict,
    variations: dict[str, dict],
    target_metric: str = "net_profit",
) -> dict:
    """`variations`: {lever_field: {"low": x, "high": y}} in the lever's own units."""
    base_levers = levers_from_params(parameters, assumptions)
    base_value = project(baseline, base_levers).metric(target_metric)

    rows = []
    for field in _LEVER_FIELDS:
        if field not in variations:
            continue
        low = float(variations[field]["low"])
        high = float(variations[field]["high"])
        low_val = project(baseline, replace(base_levers, **{field: low})).metric(target_metric)
        high_val = project(baseline, replace(base_levers, **{field: high})).metric(target_metric)
        rows.append(
            {
                "variable": field,
                "low_input": low,
                "high_input": high,
                "low_value": round(low_val, 2),
                "high_value": round(high_val, 2),
                "swing": round(abs(high_val - low_val), 2),
            }
        )
    rows.sort(key=lambda r: r["swing"], reverse=True)
    return {
        "target_metric": target_metric,
        "base_value": round(base_value, 2),
        "ranking": rows,
        "provenance": "MODEL_OUTPUT",
    }


def default_variations() -> dict[str, dict]:
    """Sensible ± bounds when the caller doesn't specify them."""
    return {
        "price_pct": {"low": -10, "high": 10},
        "demand_pct": {"low": -15, "high": 15},
        "unit_cost_pct": {"low": -10, "high": 10},
    }
