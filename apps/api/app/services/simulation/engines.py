"""General deterministic scenario engines (spec §19).

One engine class drives several scenario types (demand, supplier-cost, general
cost) via the shared projection model. `price_change` keeps its own dedicated
engine (see price_change.py) for a focused, well-documented worked example.
"""
from __future__ import annotations

from app.core.enums import ScenarioType
from app.services.analytics import BaselineEconomics
from app.services.simulation.base import (
    MetricResult,
    ScenarioOutput,
    ScenarioRequest,
    register_engine,
)
from app.services.simulation.model import REPORT_METRICS, Levers, levers_from_params, project

_BASELINE_LEVERS = Levers()


def _delta(base: float, scen: float) -> dict:
    abs_change = scen - base
    pct = (abs_change / base * 100.0) if base else 0.0
    return {"absolute": round(abs_change, 2), "percent": round(pct, 2)}


def _round_metric(metric: str, value: float) -> float:
    return round(value, 4) if metric == "gross_margin" else round(value, 2)


class GeneralScenarioEngine:
    """Handles a family of scenario types with the shared projection model."""

    model_name = "general_pnl_deterministic"
    model_version = "1.0.0"

    def __init__(self, scenario_type: str) -> None:
        self.scenario_type = scenario_type

    def run(self, request: ScenarioRequest, baseline: BaselineEconomics) -> ScenarioOutput:
        levers = levers_from_params(request.parameters, request.assumptions)
        base = project(baseline, _BASELINE_LEVERS)
        scen = project(baseline, levers)

        warnings: list[str] = []
        if baseline.units <= 0 or baseline.revenue <= 0:
            warnings.append("Insufficient sales history for a reliable baseline.")

        results = [
            MetricResult(
                metric=m,
                baseline={"value": _round_metric(m, base.metric(m))},
                scenario={"value": _round_metric(m, scen.metric(m))},
                delta=_delta(base.metric(m), scen.metric(m)),
            )
            for m in REPORT_METRICS
        ]
        return ScenarioOutput(
            results=results,
            assumptions={
                "price_elasticity": levers.elasticity,
                "price_change_percent": levers.price_pct,
                "demand_change_percent": levers.demand_pct,
                "unit_cost_change_percent": levers.unit_cost_pct,
                "fixed_opex_delta": levers.fixed_opex_delta,
                "horizon_months": request.horizon_months,
            },
            warnings=warnings,
            model_name=self.model_name,
            model_version=self.model_version,
        )


# Register the general engine for the scenario types it covers.
for _st in (
    ScenarioType.DEMAND_CHANGE,
    ScenarioType.SUPPLIER_COST_CHANGE,
    ScenarioType.COST_CHANGE,
):
    register_engine(GeneralScenarioEngine(_st.value))
