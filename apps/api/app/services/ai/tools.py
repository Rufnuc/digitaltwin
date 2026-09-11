"""Assistant tool registry (spec §32).

Each tool is a thin, read-only/compute-only wrapper over the existing analytics
and simulation services. The assistant obtains every number by calling these
tools — it never reads the database directly and never invents values. Tool
outputs are the sole source of figures in any answer.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.services.analytics import baseline_economics, dashboard_summary
from app.services.bi.customers import customer_intelligence
from app.services.bi.data_quality import data_quality_report
from app.services.bi.financials import monthly_pnl
from app.services.bi.products import product_intelligence
from app.services.bi.suppliers import supplier_intelligence
from app.services.simulation import engines, price_change  # noqa: F401  (register engines)
from app.services.simulation.base import ScenarioRequest, get_engine
from app.services.simulation.compare import compare_scenarios
from app.services.simulation.montecarlo import run_monte_carlo
from app.services.simulation.sensitivity import default_variations, tornado


@dataclass
class ToolDef:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., dict]
    # Roughly: does this tool produce a FORECAST (uncertain) or MODEL_OUTPUT?
    provenance: str = "MODEL_OUTPUT"


# --------------------------------------------------------------------------- #
# Handlers (all take the db session first, then validated kwargs).
# --------------------------------------------------------------------------- #
def _business_summary(db: Session) -> dict:
    return dashboard_summary(db)


def _financials(db: Session) -> dict:
    fin = monthly_pnl(db)
    # Trim to the last 12 months to keep the payload compact for the LLM.
    fin["series"] = fin["series"][-12:]
    return fin


def _customers(db: Session) -> dict:
    return customer_intelligence(db, top_n=5)


def _products(db: Session) -> dict:
    return product_intelligence(db, top_n=5)


def _suppliers(db: Session) -> dict:
    return supplier_intelligence(db)


def _data_quality(db: Session) -> dict:
    return data_quality_report(db)


_SCENARIO_PARAM = {
    "price_change": "price_change_percent",
    "demand_change": "demand_change_percent",
    "supplier_cost_change": "unit_cost_change_percent",
}


def _run_scenario(
    db: Session,
    scenario_type: str = "price_change",
    change_percent: float = 0.0,
    price_elasticity: float = -0.8,
    horizon_months: int = 12,
) -> dict:
    engine = get_engine(scenario_type)
    if engine is None:
        return {"error": f"unknown scenario_type '{scenario_type}'"}
    param = _SCENARIO_PARAM.get(scenario_type, "price_change_percent")
    req = ScenarioRequest(
        scenario_type=scenario_type,
        parameters={param: change_percent},
        assumptions={"price_elasticity": price_elasticity},
        horizon_months=horizon_months,
    )
    out = engine.run(req, baseline_economics(db))
    return {
        "scenario_type": scenario_type,
        "results": [
            {
                "metric": r.metric,
                "baseline": r.baseline.get("value"),
                "scenario": r.scenario.get("value"),
                "change_percent": r.delta.get("percent"),
            }
            for r in out.results
        ],
        "assumptions": out.assumptions,
        "warnings": out.warnings,
    }


def _run_monte_carlo(
    db: Session,
    price_mean: float = 0.0,
    price_std: float = 5.0,
    unit_cost_mean: float = 0.0,
    unit_cost_std: float = 5.0,
    iterations: int = 5000,
) -> dict:
    dists = {
        "price_pct": {"type": "normal", "mean": price_mean, "std": price_std},
        "unit_cost_pct": {"type": "normal", "mean": unit_cost_mean, "std": unit_cost_std},
    }
    mc = run_monte_carlo(
        baseline_economics(db), dists, iterations=iterations,
        target_metric="net_profit", target_threshold=0,
    )
    # Compact: headline stats only.
    net = mc["distributions_by_metric"]["net_profit"]
    return {
        "iterations": mc["iterations"],
        "probability_of_loss": mc["probability_of_loss"],
        "probability_net_nonnegative": mc["probability_of_target"],
        "net_profit": {"p5": net["p5"], "p50": net["p50"], "p95": net["p95"], "mean": net["mean"]},
        "sensitivity": mc["sensitivity"],
    }


def _run_sensitivity(db: Session, price_elasticity: float = -0.8) -> dict:
    return tornado(baseline_economics(db), {}, {"price_elasticity": price_elasticity},
                   default_variations(), target_metric="net_profit")


def _compare_prices(
    db: Session, price_percents: list[float] | None = None, price_elasticity: float = -0.8
) -> dict:
    percents = price_percents or [10, 5, 0]
    scenarios = [
        {
            "name": f"{p:+g}%" if p else "Hold",
            "parameters": {} if p == 0 else {"price_change_percent": p},
            "assumptions": {"price_elasticity": price_elasticity},
        }
        for p in percents
    ]
    return compare_scenarios(baseline_economics(db), scenarios)


# --------------------------------------------------------------------------- #
# Registry.
# --------------------------------------------------------------------------- #
TOOLS: list[ToolDef] = [
    ToolDef("get_business_summary", "Headline KPIs (revenue, margins, profit, orders, customers, "
            "inventory) computed from stored transactions.", {"type": "object", "properties": {}},
            _business_summary),
    ToolDef("get_financials", "Monthly profit-and-loss series for the last 12 months.",
            {"type": "object", "properties": {}}, _financials),
    ToolDef("get_customer_intelligence", "Top customers by profit, churn-risk customers "
            "(evidence-based), and revenue concentration.", {"type": "object", "properties": {}},
            _customers),
    ToolDef("get_product_intelligence", "Best sellers, most profitable products, slow movers and "
            "dead stock.", {"type": "object", "properties": {}}, _products),
    ToolDef("get_supplier_intelligence", "Supplier spend, product counts and reliability.",
            {"type": "object", "properties": {}}, _suppliers),
    ToolDef("get_data_quality", "Data-quality issues and score across the dataset.",
            {"type": "object", "properties": {}}, _data_quality),
    ToolDef(
        "run_scenario",
        "Run a deterministic what-if scenario and return baseline vs scenario for revenue, "
        "gross profit, margin, net profit and units.",
        {
            "type": "object",
            "properties": {
                "scenario_type": {"type": "string",
                                  "enum": ["price_change", "demand_change", "supplier_cost_change"]},
                "change_percent": {"type": "number",
                                   "description": "percent change, e.g. 10 or -5"},
                "price_elasticity": {"type": "number",
                                     "description": "assumed price elasticity, default -0.8"},
                "horizon_months": {"type": "integer"},
            },
            "required": ["scenario_type", "change_percent"],
        },
        _run_scenario,
    ),
    ToolDef(
        "run_monte_carlo",
        "Run a Monte Carlo simulation over uncertain price and cost changes; returns net-profit "
        "percentiles, probability of loss and input sensitivity.",
        {
            "type": "object",
            "properties": {
                "price_mean": {"type": "number"}, "price_std": {"type": "number"},
                "unit_cost_mean": {"type": "number"}, "unit_cost_std": {"type": "number"},
                "iterations": {"type": "integer"},
            },
        },
        _run_monte_carlo,
        provenance="FORECAST",
    ),
    ToolDef(
        "run_sensitivity",
        "Tornado sensitivity: which levers move net profit the most.",
        {"type": "object", "properties": {"price_elasticity": {"type": "number"}}},
        _run_sensitivity,
    ),
    ToolDef(
        "compare_price_strategies",
        "Compare several price-change strategies side by side and identify the best by net profit.",
        {
            "type": "object",
            "properties": {
                "price_percents": {"type": "array", "items": {"type": "number"}},
                "price_elasticity": {"type": "number"},
            },
        },
        _compare_prices,
    ),
]

TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


def execute_tool(db: Session, name: str, args: dict) -> dict:
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return tool.handler(db, **(args or {}))
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}


def tool_catalog() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "provenance": t.provenance} for t in TOOLS
    ]
