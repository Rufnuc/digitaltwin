"""Shared deterministic P&L projection (spec §18–§22).

A single pure function maps a business baseline plus a set of *levers* to a full
P&L. Every Phase 3 capability — deterministic scenarios, sensitivity (tornado),
Monte Carlo, and scenario comparison — is built on this one function, so all of
them reconcile with each other and with the dashboard's `pnl` identity.

Levers (all optional; defaults = no change):
    price_pct            % change in selling price
    demand_pct           exogenous % change in unit demand (on top of elasticity)
    unit_cost_pct        % change in per-unit cost (e.g. supplier price rise)
    fixed_opex_delta     absolute change in operating expenses (currency)
    elasticity           price elasticity of demand (ASSUMPTION): %ΔQ = e·%ΔP
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.analytics import BaselineEconomics


@dataclass(frozen=True)
class Levers:
    price_pct: float = 0.0
    demand_pct: float = 0.0
    unit_cost_pct: float = 0.0
    fixed_opex_delta: float = 0.0
    elasticity: float = 0.0


@dataclass(frozen=True)
class Projection:
    units: float
    revenue: float
    cogs: float
    gross_profit: float
    gross_margin: float
    operating_expenses: float
    net_profit: float
    net_margin: float

    def metric(self, name: str) -> float:
        return getattr(self, name)


def project(baseline: BaselineEconomics, levers: Levers) -> Projection:
    demand_from_price = levers.elasticity * levers.price_pct
    total_demand_pct = demand_from_price + levers.demand_pct

    units = baseline.units * (1.0 + total_demand_pct / 100.0)
    price = baseline.avg_unit_price * (1.0 + levers.price_pct / 100.0)
    unit_cost = baseline.avg_unit_cost * (1.0 + levers.unit_cost_pct / 100.0)

    revenue = units * price
    cogs = unit_cost * units
    gross_profit = revenue - cogs
    gross_margin = gross_profit / revenue if revenue else 0.0
    operating_expenses = baseline.operating_expenses + levers.fixed_opex_delta
    net_profit = gross_profit - operating_expenses
    net_margin = net_profit / revenue if revenue else 0.0

    return Projection(
        units=units,
        revenue=revenue,
        cogs=cogs,
        gross_profit=gross_profit,
        gross_margin=gross_margin,
        operating_expenses=operating_expenses,
        net_profit=net_profit,
        net_margin=net_margin,
    )


# Metrics reported by Phase 3 engines (order matters for display).
REPORT_METRICS = ("revenue", "gross_profit", "gross_margin", "net_profit", "units")


def levers_from_params(parameters: dict, assumptions: dict) -> Levers:
    """Build Levers from a stored scenario's parameters + assumptions."""
    return Levers(
        price_pct=float(parameters.get("price_change_percent", 0.0)),
        demand_pct=float(parameters.get("demand_change_percent", 0.0)),
        unit_cost_pct=float(parameters.get("unit_cost_change_percent", 0.0)),
        fixed_opex_delta=float(parameters.get("fixed_opex_delta", 0.0)),
        elasticity=float(assumptions.get("price_elasticity", 0.0)),
    )
