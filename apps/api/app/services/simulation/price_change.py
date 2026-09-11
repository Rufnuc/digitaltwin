"""Deterministic price-change scenario (spec §21).

Given the business baseline and a price change %, applies a constant-elasticity
demand response and recomputes revenue, gross profit and margin. Elasticity is an
explicit ASSUMPTION surfaced in the output — never hidden. This is intentionally a
transparent, closed-form model; probabilistic ranges are added in Phase 3 (Monte
Carlo) behind the same interface.
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

DEFAULT_ELASTICITY = -0.8  # conservative default; %ΔQ = elasticity * %ΔP


def _delta(base: float, scen: float) -> dict:
    abs_change = scen - base
    pct = (abs_change / base * 100.0) if base else 0.0
    return {"absolute": round(abs_change, 2), "percent": round(pct, 2)}


class PriceChangeEngine:
    scenario_type = ScenarioType.PRICE_CHANGE.value
    model_name = "price_change_deterministic"
    model_version = "1.0.0"

    def run(self, request: ScenarioRequest, baseline: BaselineEconomics) -> ScenarioOutput:
        warnings: list[str] = []
        price_change_pct = float(request.parameters.get("price_change_percent", 0.0))
        elasticity = float(request.assumptions.get("price_elasticity", DEFAULT_ELASTICITY))

        if baseline.units <= 0 or baseline.revenue <= 0:
            warnings.append(
                "Insufficient sales history to establish a baseline; results are unreliable."
            )

        demand_change_pct = elasticity * price_change_pct
        unit_factor = 1.0 + demand_change_pct / 100.0
        price_factor = 1.0 + price_change_pct / 100.0

        new_units = baseline.units * unit_factor
        new_price = baseline.avg_unit_price * price_factor
        new_revenue = new_units * new_price
        new_cogs = baseline.avg_unit_cost * new_units  # unit cost unchanged by assumption
        new_gross_profit = new_revenue - new_cogs
        new_margin = new_gross_profit / new_revenue if new_revenue else 0.0

        results = [
            MetricResult(
                metric="revenue",
                baseline={"value": round(baseline.revenue, 2)},
                scenario={"value": round(new_revenue, 2)},
                delta=_delta(baseline.revenue, new_revenue),
            ),
            MetricResult(
                metric="gross_profit",
                baseline={"value": round(baseline.gross_profit, 2)},
                scenario={"value": round(new_gross_profit, 2)},
                delta=_delta(baseline.gross_profit, new_gross_profit),
            ),
            MetricResult(
                metric="gross_margin",
                baseline={"value": round(baseline.gross_margin, 4)},
                scenario={"value": round(new_margin, 4)},
                delta=_delta(baseline.gross_margin, new_margin),
            ),
            MetricResult(
                metric="units_sold",
                baseline={"value": round(baseline.units, 2)},
                scenario={"value": round(new_units, 2)},
                delta=_delta(baseline.units, new_units),
                detail="Demand response from assumed price elasticity.",
            ),
        ]

        return ScenarioOutput(
            results=results,
            assumptions={
                "price_elasticity": elasticity,
                "price_change_percent": price_change_pct,
                "implied_demand_change_percent": round(demand_change_pct, 2),
                "unit_cost_held_constant": True,
                "horizon_months": request.horizon_months,
                "_note": "Elasticity is an ASSUMPTION, not measured from data in Phase 1.",
            },
            warnings=warnings,
            model_name=self.model_name,
            model_version=self.model_version,
        )


register_engine(PriceChangeEngine())
