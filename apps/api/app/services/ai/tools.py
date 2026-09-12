"""Assistant tool registry (spec §32).

Read/compute tools are thin wrappers over the analytics and simulation services;
the assistant obtains every number by calling them and never invents values.

The assistant is also a **connected control layer**: `mutating` action tools let
it make changes across the platform (create/update records, refresh market data,
run and save simulations). Every action is role-gated to the current user's
permissions and audit-logged.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction, DataOrigin, Role
from app.core.security import role_at_least
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.product import Product, ProductPriceHistory
from app.models.simulation import SimulationRun
from app.services import audit
from app.services.agents import simulation as agent_sim
from app.services.analytics import baseline_economics, dashboard_summary
from app.services.bi.customers import customer_intelligence
from app.services.bi.data_quality import data_quality_report
from app.services.bi.financials import monthly_pnl
from app.services.bi.products import product_intelligence
from app.services.bi.suppliers import supplier_intelligence
from app.services.impact import engine as impact_engine
from app.services.market_intelligence import ingest as market_ingest
from app.services.simulation import engines, price_change  # noqa: F401  (register engines)
from app.services.simulation.base import ScenarioRequest, get_engine
from app.services.simulation.compare import compare_scenarios
from app.services.simulation.montecarlo import run_monte_carlo
from app.services.simulation.runner import run_simulation
from app.services.simulation.sensitivity import default_variations, tornado


@dataclass
class ToolDef:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., dict]
    # Roughly: does this tool produce a FORECAST (uncertain) or MODEL_OUTPUT?
    provenance: str = "MODEL_OUTPUT"
    # Action tools change data; they are role-gated and audit-logged.
    mutating: bool = False
    min_role: str = Role.VIEWER.value


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
# Action handlers (mutating) — the assistant's connected control layer.
# --------------------------------------------------------------------------- #
def _next_code(db: Session, model, prefix: str) -> str:
    n = int(db.scalar(select(func.count(model.id))) or 0)
    return f"{prefix}-{n + 1:04d}"


def _create_customer(db: Session, name: str, location: str | None = None,
                     customer_type: str = "RETAIL") -> dict:
    c = Customer(code=_next_code(db, Customer, "CUS"), name=name, location=location,
                 customer_type=customer_type, data_origin=DataOrigin.REAL.value)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"created": "customer", "id": c.id, "code": c.code, "name": c.name}


def _find_customer(db: Session, query: str):
    q = (query or "").strip()
    return db.scalar(
        select(Customer).where(or_(Customer.code == q, Customer.name.ilike(f"%{q}%")))
    )


def _set_customer_status(db: Session, customer: str, status: str) -> dict:
    c = _find_customer(db, customer)
    if not c:
        return {"error": f"customer '{customer}' not found"}
    old, c.status = c.status, status.upper()
    db.commit()
    return {"updated": "customer", "id": c.id, "name": c.name,
            "status_from": old, "status_to": c.status}


def _create_product(db: Session, name: str, purchase_cost: float, selling_price: float,
                    category: str | None = None) -> dict:
    p = Product(code=_next_code(db, Product, "PRD"), name=name, purchase_cost=purchase_cost,
                selling_price=selling_price, category=category, data_origin=DataOrigin.REAL.value)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"created": "product", "id": p.id, "code": p.code, "name": p.name,
            "selling_price": float(p.selling_price)}


def _find_product(db: Session, query: str):
    q = (query or "").strip()
    return db.scalar(select(Product).where(
        or_(Product.code == q, Product.part_number == q, Product.name.ilike(f"%{q}%"))
    ))


def _set_product_price(db: Session, product: str, selling_price: float) -> dict:
    p = _find_product(db, product)
    if not p:
        return {"error": f"product '{product}' not found"}
    old = float(p.selling_price) if p.selling_price is not None else None
    p.selling_price = selling_price
    db.add(ProductPriceHistory(product_id=p.id, effective_date=date.today(),
                               selling_price=selling_price, purchase_cost=p.purchase_cost))
    db.commit()
    return {"updated": "product", "id": p.id, "name": p.name,
            "price_from": old, "price_to": selling_price}


def _set_product_cost(db: Session, product: str, purchase_cost: float) -> dict:
    p = _find_product(db, product)
    if not p:
        return {"error": f"product '{product}' not found"}
    old = float(p.purchase_cost) if p.purchase_cost is not None else None
    p.purchase_cost = purchase_cost
    db.add(ProductPriceHistory(product_id=p.id, effective_date=date.today(),
                               purchase_cost=purchase_cost, selling_price=p.selling_price))
    db.commit()
    return {"updated": "product_cost", "id": p.id, "name": p.name,
            "cost_from": old, "cost_to": purchase_cost}


def _set_inventory(db: Session, product: str, quantity: float | None = None,
                   unit_cost: float | None = None, safety_stock: float | None = None) -> dict:
    p = _find_product(db, product)
    if not p:
        return {"error": f"product '{product}' not found"}
    inv = db.scalar(select(Inventory).where(Inventory.product_id == p.id))
    if inv is None:
        inv = Inventory(product_id=p.id, quantity_on_hand=0, data_origin=DataOrigin.REAL.value)
        db.add(inv)
    changed: dict = {}
    if quantity is not None:
        inv.quantity_on_hand = int(quantity)
        changed["quantity_on_hand"] = int(quantity)
    if unit_cost is not None:
        inv.unit_cost = unit_cost
        changed["unit_cost"] = unit_cost
    if safety_stock is not None:
        inv.safety_stock = int(safety_stock)
        changed["safety_stock"] = int(safety_stock)
    if not changed:
        return {"error": "nothing to update: provide quantity, unit_cost or safety_stock"}
    db.commit()
    return {"updated": "inventory", "product": p.name, "product_id": p.id, **changed}


def _refresh_market(db: Session) -> dict:
    return market_ingest.refresh_market_data(db)


def _scan_impact(db: Session) -> dict:
    r = impact_engine.scan(db)
    return {"assessments": len(r["assessments"]), "alerts_created": r["alerts_created"],
            "has_market_data": r["has_market_data"]}


def _save_simulation(db: Session, scenario_type: str = "price_change", change_percent: float = 0.0,
                     price_elasticity: float = -0.8, name: str | None = None) -> dict:
    param = _SCENARIO_PARAM.get(scenario_type, "price_change_percent")
    run = SimulationRun(
        name=name or f"{scenario_type} {change_percent:+g}%", scenario_type=scenario_type,
        parameters={param: change_percent}, assumptions={"price_elasticity": price_elasticity},
        horizon_months=12, status="PENDING",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run = run_simulation(db, run)
    return {
        "created": "simulation", "id": run.id, "status": run.status,
        "results": [
            {"metric": r.metric, "baseline": r.baseline.get("value"),
             "scenario": r.scenario.get("value"), "change_percent": r.delta.get("percent")}
            for r in run.results
        ],
    }


# Behavioural levers the assistant may tune on the digital-twin agents. Kept as an
# allow-list so the model can only touch known assumptions (each defaults from
# agent_sim.DEFAULT_ASSUMPTIONS when omitted).
_AGENT_ASSUMPTION_KEYS = (
    "price_elasticity",
    "base_monthly_churn",
    "churn_risk_multiplier",
    "competitor_price_index",
    "competitor_sensitivity",
    "macro_demand_drag",
    "fx_annual_depreciation",
)


def _pick_assumptions(kwargs: dict) -> dict:
    """Collect any behavioural-assumption overrides the caller supplied."""
    return {k: float(kwargs[k]) for k in _AGENT_ASSUMPTION_KEYS if kwargs.get(k) is not None}


def _describe_agents(db: Session) -> dict:
    """The digital-twin agent roster and the levers the assistant can tune."""
    return {
        "agents": agent_sim.AGENT_ROSTER,
        "default_assumptions": agent_sim.DEFAULT_ASSUMPTIONS,
        "tunable_assumptions": list(_AGENT_ASSUMPTION_KEYS),
        "policy_levers": ["price_change_percent", "monthly_opex_delta"],
        "note": "Agents are calibrated from REAL data; behaviour is ASSUMPTION; "
                "outcomes are FORECASTS with uncertainty.",
    }


def _agent_forecast(db: Session, price_change_percent: float = 0.0,
                    monthly_opex_delta: float = 0.0, horizon_months: int = 12,
                    iterations: int = 300, **assumptions) -> dict:
    policy = {"price_change_percent": float(price_change_percent),
              "monthly_opex_delta": float(monthly_opex_delta)}
    overrides = _pick_assumptions(assumptions)
    res = agent_sim.simulate(db, policy, horizon_months, iterations, overrides or None)
    if res is None:
        return {"error": "no customer data to calibrate agents"}
    return {"policy": res["policy"],
            "horizon_months": res["horizon_months"],
            "iterations": res["iterations"],
            "cumulative_net_profit": res["cumulative_net_profit"],
            "probability_of_loss": res["probability_of_cumulative_loss"],
            "expected_active_customers_end": res["expected_active_customers_end"],
            "customers_start": res["customers_start"],
            "assumptions_used": res["assumptions"],
            "provenance": res["provenance"]}


def _compare_agent_strategies(db: Session, strategies: list | None = None,
                              horizon_months: int = 12, iterations: int = 300,
                              **assumptions) -> dict:
    """Run several named policies through the agents and rank them by expected profit."""
    if not strategies:
        return {"error": "provide a list of strategies, each with a name and "
                         "price_change_percent (and optional monthly_opex_delta)"}
    norm = []
    for i, s in enumerate(strategies):
        s = s or {}
        norm.append({
            "name": str(s.get("name", f"strategy {i + 1}")),
            "price_change_percent": float(s.get("price_change_percent", 0.0)),
            "monthly_opex_delta": float(s.get("monthly_opex_delta", 0.0)),
        })
    overrides = _pick_assumptions(assumptions)
    res = agent_sim.compare_policies(db, norm, horizon_months, iterations, overrides or None)
    if res is None:
        return {"error": "no customer data to calibrate agents"}
    return res


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
                "scenario_type": {
                    "type": "string",
                    "enum": ["price_change", "demand_change", "supplier_cost_change"],
                },
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
    # ---- Action tools (mutating; role-gated + audit-logged) ----
    ToolDef(
        "create_customer", "Create a new customer record.",
        {"type": "object",
         "properties": {"name": {"type": "string"}, "location": {"type": "string"},
                        "customer_type": {"type": "string"}},
         "required": ["name"]},
        _create_customer, provenance="REAL", mutating=True, min_role=Role.STAFF.value,
    ),
    ToolDef(
        "set_customer_status", "Set a customer's status (e.g. ACTIVE / INACTIVE) by name or code.",
        {"type": "object",
         "properties": {"customer": {"type": "string"}, "status": {"type": "string"}},
         "required": ["customer", "status"]},
        _set_customer_status, provenance="REAL", mutating=True, min_role=Role.STAFF.value,
    ),
    ToolDef(
        "create_product", "Create a new product with cost and selling price.",
        {"type": "object",
         "properties": {"name": {"type": "string"}, "purchase_cost": {"type": "number"},
                        "selling_price": {"type": "number"}, "category": {"type": "string"}},
         "required": ["name", "purchase_cost", "selling_price"]},
        _create_product, provenance="REAL", mutating=True, min_role=Role.STAFF.value,
    ),
    ToolDef(
        "set_product_price", "Change a product's selling price by name or code.",
        {"type": "object",
         "properties": {"product": {"type": "string"}, "selling_price": {"type": "number"}},
         "required": ["product", "selling_price"]},
        _set_product_price, provenance="REAL", mutating=True, min_role=Role.STAFF.value,
    ),
    ToolDef(
        "set_product_cost", "Change a product's purchase (unit) cost by name or code.",
        {"type": "object",
         "properties": {"product": {"type": "string"}, "purchase_cost": {"type": "number"}},
         "required": ["product", "purchase_cost"]},
        _set_product_cost, provenance="REAL", mutating=True, min_role=Role.STAFF.value,
    ),
    ToolDef(
        "set_inventory",
        "Update a product's inventory — quantity on hand, unit cost, and/or safety stock.",
        {"type": "object",
         "properties": {"product": {"type": "string"}, "quantity": {"type": "number"},
                        "unit_cost": {"type": "number"}, "safety_stock": {"type": "number"}},
         "required": ["product"]},
        _set_inventory, provenance="REAL", mutating=True, min_role=Role.STAFF.value,
    ),
    ToolDef(
        "refresh_market_data",
        "Fetch the latest real economic data (World Bank, FX) and news, and store it.",
        {"type": "object", "properties": {}},
        _refresh_market, provenance="REAL", mutating=True, min_role=Role.ANALYST.value,
    ),
    ToolDef(
        "run_impact_scan",
        "Assess how current market signals could affect the business and raise dashboard alerts.",
        {"type": "object", "properties": {}},
        _scan_impact, provenance="MODEL_OUTPUT", mutating=True, min_role=Role.ANALYST.value,
    ),
    ToolDef(
        "save_simulation",
        "Create and run a scenario, saving it to the simulations history.",
        {"type": "object",
         "properties": {"scenario_type": {"type": "string"}, "change_percent": {"type": "number"},
                        "price_elasticity": {"type": "number"}, "name": {"type": "string"}},
         "required": ["scenario_type", "change_percent"]},
        _save_simulation, provenance="MODEL_OUTPUT", mutating=True, min_role=Role.ANALYST.value,
    ),
    ToolDef(
        "describe_agents",
        "List the digital-twin agents (Customer, Supplier, Competitor, Market), how each is "
        "calibrated, and the behavioural assumptions and policy levers you can tune. Call this "
        "first when the user asks about, or wants to steer, the agents.",
        {"type": "object", "properties": {}},
        _describe_agents, provenance="MODEL_OUTPUT", mutating=False, min_role=Role.VIEWER.value,
    ),
    ToolDef(
        "run_agent_forecast",
        "Run the multi-agent digital-twin Monte Carlo forecast for a business policy. Tune the "
        "policy (price change, monthly opex delta) and any behavioural assumptions to steer how "
        "the agents behave. Returns a distribution (mean/p5/p95) of cumulative net profit, the "
        "probability of loss, and expected customers retained. Outcomes are FORECASTS.",
        {"type": "object", "properties": {
            "price_change_percent": {"type": "number",
                                     "description": "our price change, e.g. 10 or -5"},
            "monthly_opex_delta": {"type": "number",
                                   "description": "change to monthly operating expenses (₦)"},
            "horizon_months": {"type": "integer", "description": "months to simulate (1-60)"},
            "iterations": {"type": "integer", "description": "Monte Carlo iterations (50-5000)"},
            "price_elasticity": {"type": "number",
                                 "description": "demand response to price (default -0.8)"},
            "base_monthly_churn": {"type": "number",
                                   "description": "monthly churn hazard (default 0.02)"},
            "churn_risk_multiplier": {"type": "number",
                                      "description": "×hazard for at-risk customers (default 3)"},
            "competitor_price_index": {"type": "number",
                                       "description": "competitor price ÷ our baseline (def 1)"},
            "competitor_sensitivity": {"type": "number",
                                       "description": "demand lost per unit price premium (0.5)"},
            "macro_demand_drag": {"type": "number",
                                  "description": "fraction of inflation that dampens demand (0.3)"},
            "fx_annual_depreciation": {"type": "number",
                                       "description": "extra annual cost drift from FX (def 0)"},
        }},
        _agent_forecast, provenance="FORECAST", mutating=False, min_role=Role.VIEWER.value,
    ),
    ToolDef(
        "compare_agent_strategies",
        "Run several named policies through the digital-twin agents and rank them by expected "
        "cumulative net profit (with p5/p95 and probability of loss). Use this to answer 'which "
        "strategy is best?'. Behavioural assumptions apply to every strategy for fairness.",
        {"type": "object", "properties": {
            "strategies": {
                "type": "array",
                "description": "policies to compare",
                "items": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "price_change_percent": {"type": "number"},
                    "monthly_opex_delta": {"type": "number"},
                }},
            },
            "horizon_months": {"type": "integer"},
            "iterations": {"type": "integer"},
            "price_elasticity": {"type": "number"},
            "base_monthly_churn": {"type": "number"},
            "competitor_price_index": {"type": "number"},
            "macro_demand_drag": {"type": "number"},
        }, "required": ["strategies"]},
        _compare_agent_strategies, provenance="FORECAST", mutating=False,
        min_role=Role.VIEWER.value,
    ),
]

TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


def _audit_action(name: str) -> AuditAction:
    if name.startswith("create_"):
        return AuditAction.CREATE
    if name.startswith("set_"):
        return AuditAction.UPDATE
    return AuditAction.RUN_SIMULATION


def execute_tool(db: Session, name: str, args: dict, user=None) -> dict:
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return {"error": f"unknown tool '{name}'"}
    if tool.mutating:
        if user is None:
            return {"error": "this action requires an authenticated user"}
        if not role_at_least(user.role, tool.min_role):
            return {"error": f"'{name}' requires role {tool.min_role} or higher "
                             f"(you are {user.role})"}
    try:
        result = tool.handler(db, **(args or {}))
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    if tool.mutating and user is not None and "error" not in result:
        audit.record(db, action=_audit_action(name), user_id=user.id,
                     entity_type=f"assistant:{name}", summary=str(result)[:400])
    return result


def tool_catalog() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "provenance": t.provenance,
         "mutating": t.mutating, "min_role": t.min_role}
        for t in TOOLS
    ]
