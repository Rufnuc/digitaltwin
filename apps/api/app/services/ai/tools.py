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
from app.models.invoice import Invoice
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


def _data_provenance(db: Session) -> dict:
    """Honest demo-vs-real split of the sales data an analysis rests on."""
    total = int(db.scalar(select(func.count()).select_from(Invoice)) or 0)
    demo = int(db.scalar(
        select(func.count()).select_from(Invoice)
        .where(Invoice.data_origin == DataOrigin.DEMO.value)
    ) or 0)
    real = total - demo
    if total == 0:
        basis = "NO_DATA"
    elif demo == total:
        basis = "ALL_DEMO"
    elif demo == 0:
        basis = "ALL_REAL"
    else:
        basis = "MIXED"
    return {
        "invoices_total": total, "invoices_demo": demo, "invoices_real": real,
        "basis": basis,
        "note": ("This analysis is based on DEMO/synthetic seed data, not real "
                 "transactions — do not present the figures as real."
                 if basis in ("ALL_DEMO", "MIXED") else
                 "This analysis is based on real recorded transactions."
                 if basis == "ALL_REAL" else "No sales data yet."),
    }


def _full_business_analysis(db: Session) -> dict:
    """One-shot, comprehensive business analysis: gathers KPIs, the P&L trend,
    customer and product intelligence, ABC and data quality so the assistant can
    synthesise insights without chaining many tool calls."""
    prov = _data_provenance(db)
    fin = monthly_pnl(db)
    fin["series"] = fin["series"][-6:]  # last 6 months, compact
    abc_summary = None
    reorder_summary = None
    try:
        from app.services.quant import enabled as quant_enabled
        from app.services.quant import service as qsvc
        if quant_enabled():
            abc = qsvc.abc_report(db)
            abc_summary = {"counts": abc.get("counts"), "top": abc.get("items", [])[:5]}
            # Embed the reorder brain: what to restock now + the capital needed.
            scan = qsvc.reorder_scan(db)
            reorder_summary = {
                "counts": scan["counts"],
                "total_estimated_restock_cost": scan["total_estimated_restock_cost"],
                "order_now": [
                    {"product": i["product_name"], "code": i["product_code"],
                     "abc_class": i.get("abc_class"),
                     "quantity": i["recommended_order_quantity"],
                     "estimated_cost": i["estimated_order_cost"],
                     "margin_at_risk": i.get("margin_at_risk_over_horizon")}
                    for i in scan["items"] if i["recommendation_status"] == "READY"
                ][:8],
            }
    except Exception:  # noqa: BLE001 — quant is optional
        pass
    money = None
    try:
        from app.services import cashflow, payables, receivables
        rec = receivables.receivables_summary(db)
        pay = payables.payables_summary(db)
        cf = cashflow.cash_flow_summary(db, days=30)
        money = {
            "owed_to_us": rec["total_outstanding"],
            "receivables_overdue": rec["overdue_total"],
            "we_owe_suppliers": pay["total_payable"],
            "net_position": cf["net_position"],
            "money_in_30d": cf["money_in"], "money_out_30d": cf["money_out"],
            "net_cash_flow_30d": cf["net_cash_flow"],
        }
    except Exception:  # noqa: BLE001 — money layer is optional
        pass
    return {
        "data_provenance": prov,
        "kpis": dashboard_summary(db),
        "pnl_trend_6mo": fin,
        "money": money,
        "customers": customer_intelligence(db, top_n=5),
        "products": product_intelligence(db),
        "suppliers": supplier_intelligence(db),
        "abc": abc_summary,
        "reorder_plan": reorder_summary,
        "data_quality": data_quality_report(db),
        "guidance": ("Synthesise these into 4-6 concrete insights and prioritised "
                     "recommendations. State the data provenance honestly. If a "
                     "reorder_plan is present, include what to restock and the "
                     "capital it needs as one of the recommendations."),
    }


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
# Quant module tools (deterministic forecasting / reorder / ABC).
# --------------------------------------------------------------------------- #
def _resolve_product_id(db: Session, product_id=None, product=None) -> int | None:
    if product_id is not None:
        try:
            return int(product_id)
        except (TypeError, ValueError):
            return None
    if product:
        row = db.scalar(
            select(Product).where(
                or_(Product.code == str(product), Product.name.ilike(f"%{product}%"))
            )
        )
        return row.id if row else None
    return None


def _resolve_customer_id(db: Session, customer=None, customer_id=None) -> int | None:
    if customer_id is not None:
        try:
            return int(customer_id)
        except (TypeError, ValueError):
            return None
    if customer:
        row = db.scalar(select(Customer).where(
            or_(Customer.code == str(customer), Customer.name.ilike(f"%{customer}%"))
        ))
        return row.id if row else None
    return None


# --------------------------------------------------------------------------- #
# Money — accounts receivable (who owes what, record payments).
# --------------------------------------------------------------------------- #
def _receivables_summary(db: Session) -> dict:
    from app.services import receivables
    r = receivables.receivables_summary(db)
    return {
        "total_outstanding": r["total_outstanding"], "overdue_total": r["overdue_total"],
        "aging": r["aging"], "open_invoices": r["open_invoice_count"],
        "top_debtors": [
            {"customer": d["customer_name"], "owes": d["outstanding"]}
            for d in r["debtors"][:10]
        ],
    }


def _overdue_receivables(db: Session) -> dict:
    from app.services import receivables
    r = receivables.overdue_invoices(db)
    return {
        "overdue_count": r["count"], "overdue_total": r["total"],
        "invoices": [
            {"invoice": i["invoice_number"], "customer": i["customer_name"],
             "balance": i["balance"], "days_overdue": i["days_overdue"]}
            for i in r["invoices"][:20]
        ],
    }


def _customer_balance(db: Session, customer=None, customer_id=None) -> dict:
    from app.services import receivables
    cid = _resolve_customer_id(db, customer=customer, customer_id=customer_id)
    if cid is None:
        return {"error": "customer not found; give a customer name or code"}
    st = receivables.customer_statement(db, cid)
    if st.get("status") == "NOT_FOUND":
        return {"error": "customer not found"}
    return {
        "customer": st["customer_name"], "outstanding": st["outstanding"],
        "credit_limit": st["credit_limit"],
        "recent": st["events"][-8:],
    }


def _record_payment(db: Session, invoice_number=None, invoice_id=None, amount: float = 0.0,
                    method: str = "cash", reference=None) -> dict:
    from app.services import receivables
    inv_id = invoice_id
    if inv_id is None and invoice_number:
        row = db.scalar(select(Invoice).where(Invoice.invoice_number == str(invoice_number)))
        inv_id = row.id if row else None
    if inv_id is None:
        return {"error": "give the invoice number (or id) to pay against"}
    r = receivables.record_payment(db, invoice_id=int(inv_id), amount=float(amount),
                                   method=method, reference=reference)
    return r


def _payables_summary(db: Session) -> dict:
    from app.services import payables
    r = payables.payables_summary(db)
    return {
        "total_payable": r["total_payable"], "overdue_total": r["overdue_total"],
        "aging": r["aging"], "open_purchases": r["open_purchase_count"],
        "top_creditors": [
            {"supplier": c["supplier_name"], "we_owe": c["owed"]}
            for c in r["creditors"][:10]
        ],
    }


def _cash_flow(db: Session, days: int = 30) -> dict:
    from app.services import cashflow
    return cashflow.cash_flow_summary(db, days=int(days))


def _quant_forecast(db: Session, product_id=None, product=None, horizon_periods: int = 12) -> dict:
    from app.services.quant import service as qsvc

    pid = _resolve_product_id(db, product_id, product)
    if pid is None:
        return {"error": "product not found; give a product id, code or name"}
    r = qsvc.product_forecast(db, pid, horizon=int(horizon_periods))
    f = r.get("forecast", {})
    bridge = r.get("daily_bridge", {})
    return {
        "product": r.get("product_name"), "code": r.get("product_code"),
        "status": r.get("status"), "pattern": r.get("classification", {}).get("pattern"),
        "model": f.get("model_name"), "point_per_week": f.get("point_values", [None])[0],
        "quantiles_week1": {k: v[0] for k, v in f.get("quantiles", {}).items()},
        "weeks_observed": r.get("demand", {}).get("weeks_observed"),
        # Weekly→daily split feeding day-level planning.
        "daily_split": {
            "method": bridge.get("method"),
            "expected_per_day": bridge.get("expected_daily_means"),
        },
    }


def _quant_reorder(db: Session, product_id=None, product=None, service_level=None) -> dict:
    from app.services.quant import service as qsvc

    pid = _resolve_product_id(db, product_id, product)
    if pid is None:
        return {"error": "product not found; give a product id, code or name"}
    # None -> ABC-aware service level (A items protected more).
    sl = float(service_level) if service_level is not None else None
    r = qsvc.product_reorder(db, pid, service_level=sl)
    if r.get("status") != "OK":
        return {"product": r.get("product_name"), "status": r.get("status"),
                "missing_fields": r.get("missing_fields")}
    rec = r["recommendation"]
    lt = r.get("lead_time", {})
    return {
        "product": r.get("product_name"), "pattern": r.get("pattern"),
        "abc_class": r.get("abc_class"), "applied_service_level": r.get("applied_service_level"),
        "margin_at_risk_over_horizon": r.get("margin_at_risk_over_horizon"),
        "recommended_order_quantity": rec["recommended_order_quantity"],
        "safety_stock": rec["safety_stock"], "order_up_to_level": rec["order_up_to_level"],
        "protection_horizon_days": rec["protection_horizon_days"],
        "recommendation_status": rec["recommendation_status"], "warnings": rec["warnings"],
        "estimated_order_cost": rec.get("estimated_order_cost"),
        # Lead-time evidence behind the safety stock.
        "lead_time": {
            "mean_days": lt.get("mean_days"), "std_days": lt.get("std_days"),
            "risk": lt.get("lead_time_risk"), "source": lt.get("source"),
        },
    }


def _quant_abc(db: Session) -> dict:
    from app.services.quant import service as qsvc

    r = qsvc.abc_report(db)
    return {"counts": r.get("counts"), "total_value": r.get("total_value"),
            "top": r.get("items", [])[:15], "new_products": r.get("new_products", [])[:10]}


def _quant_portfolio_risk(db: Session, horizon_days: int = 90) -> dict:
    """Whole-catalogue stockout exposure from a portfolio Monte Carlo."""
    from app.services.quant import service as qsvc

    r = qsvc.portfolio_simulation(db, horizon_days=int(horizon_days), iterations=400)
    if r.get("status") != "OK":
        return {"status": r.get("status"), "warnings": r.get("warnings")}
    pf = r["portfolio"]
    return {
        "products_simulated": r["products_simulated"],
        "horizon_days": pf["horizon_days"],
        "probability_any_product_stockout": pf["probability_of_any_stockout"],
        "expected_stockout_product_fraction": pf["expected_stockout_product_fraction"],
        "expected_portfolio_fill_rate": pf["expected_portfolio_fill_rate"],
        "expected_portfolio_cycle_service_level": pf["expected_portfolio_cycle_service_level"],
        "highest_risk_products": [
            {"product": w.get("product_name"), "probability_of_stockout":
             w["probability_of_stockout"]}
            for w in pf["highest_risk_products"]
        ],
        "note": "Monte-Carlo FORECAST across the catalogue; not a certainty.",
    }


def _activity_log(db: Session, entity_type=None, product=None, action=None,
                  limit: int = 20) -> dict:
    """Recent activity from the automatic audit trail (who changed what, when)."""
    from app.services import audit

    entity_id = None
    if product is not None:
        pid = _resolve_product_id(db, product=product)
        if pid is not None:
            entity_type, entity_id = "products", pid
    r = audit.list_audit(db, entity_type=entity_type, entity_id=entity_id,
                         action=action, limit=min(int(limit), 50))
    return {
        "total_matching": r["total"],
        "events": [
            {"when": e["at"], "who": e["user_name"] or "system", "what": e["summary"],
             "action": e["action"], "source": e["source"],
             "entity": (f"{e['entity_type']} #{e['entity_id']}"
                        if e["entity_id"] else e["entity_type"])}
            for e in r["items"]
        ],
        "note": "From the automatic audit trail — every create/update/delete is recorded.",
    }


def _quant_landed_cost(db: Session, product_id=None, product=None) -> dict:
    """Estimated landed cost (base + import uplifts) for a product."""
    from app.services.quant import supplier as sup

    pid = _resolve_product_id(db, product_id, product)
    if pid is None:
        return {"error": "product not found; give a product id, code or name"}
    prod = db.get(Product, pid)
    if prod is None or prod.purchase_cost is None:
        return {"product": getattr(prod, "name", None), "status": "INSUFFICIENT_DATA",
                "missing_fields": ["unit_cost"]}
    lc = sup.estimate_landed_cost(float(prod.purchase_cost))
    return {
        "product": prod.name, "base_unit_cost": float(prod.purchase_cost),
        "total_landed_cost": lc["total_landed_cost"],
        "total_uplift_pct": lc["total_uplift_pct"],
        "components": lc["components"],
        "configured": lc["configured"],
        "note": lc["note"] or "Landed-cost uplifts are configured from real figures.",
    }


def _quant_supplier_scores(db: Session) -> dict:
    """Risk-adjusted supplier scores from reliability and realised lead times."""
    from app.services.quant import service as qsvc

    r = qsvc.supplier_scores(db)
    return {
        "counts": r["counts"],
        "suppliers": [
            {"supplier": s["supplier_name"], "code": s["supplier_code"],
             "score": s["score"], "supplier_risk": s["supplier_risk"],
             "reliability": s["components"]["reliability"],
             "lead_time_mean_days": s["components"]["lead_time_mean_days"],
             "lead_time_risk": s["components"]["lead_time_risk"],
             "status": s["status"]}
            for s in r["suppliers"]
        ][:25],
        "note": "Composite of configured reliability and realised lead-time "
                "consistency/length; weights are assumptions.",
    }


def _quant_budget_plan(db: Session, budget: float = 0.0, service_level=None) -> dict:
    """Budget-constrained reorder plan: what to buy with a fixed restock budget."""
    from app.services.quant import service as qsvc

    if not budget or float(budget) <= 0:
        return {"error": "give a positive restock budget (in Naira)"}
    sl = float(service_level) if service_level is not None else None
    plan = qsvc.budget_reorder_plan(db, float(budget), service_level=sl)
    return {
        "budget": plan["budget"], "allocated_spend": plan["allocated_spend"],
        "remaining_budget": plan["remaining_budget"],
        "margin_at_risk_protected": plan["margin_at_risk_protected"],
        "margin_at_risk_unfunded": plan["margin_at_risk_unfunded"],
        "buy": [
            {"product": f["product_name"], "code": f["product_code"],
             "abc_class": f["abc_class"], "quantity": f["recommended_order_quantity"],
             "cost": f["estimated_order_cost"],
             "margin_protected": f["margin_at_risk_protected"]}
            for f in plan["funded"]
        ][:25],
        "skipped_no_budget": [
            {"product": d["product_name"], "code": d["product_code"],
             "cost": d["estimated_order_cost"],
             "margin_at_risk": d["margin_at_risk_protected"]}
            for d in plan["deferred"]
        ][:15],
        "needs_review_count": plan["needs_review_count"],
        "assumptions": plan["assumptions"],
    }


def _quant_stockout_risk(db: Session, product_id=None, product=None,
                         horizon_days: int = 90) -> dict:
    """Simulated stockout risk / service level for one product under its policy."""
    from app.services.quant import service as qsvc

    pid = _resolve_product_id(db, product_id, product)
    if pid is None:
        return {"error": "product not found; give a product id, code or name"}
    r = qsvc.product_simulation(db, pid, horizon_days=int(horizon_days))
    if r.get("status") != "OK":
        return {"product": r.get("product_name"), "status": r.get("status"),
                "missing_fields": r.get("missing_fields")}
    s = r["simulation"]
    return {
        "product": r.get("product_name"), "abc_class": r.get("abc_class"),
        "horizon_days": s["horizon_days"], "iterations": s["iterations"],
        "probability_of_stockout": s["probability_of_stockout"],
        "expected_fill_rate": s["expected_fill_rate"],
        "expected_cycle_service_level": s["expected_cycle_service_level"],
        "expected_lost_units": s["expected_lost_units"],
        "stockout_cost": r["stockout_cost"],
        "substitute_cover": {
            "in_stock_substitutes": r["substitute_cover"]["substitutes_in_stock"],
            "total_substitute_on_hand": r["substitute_cover"]["total_substitute_on_hand"],
            "has_cover": r["substitute_cover"]["has_cover"],
        },
        "note": "Monte-Carlo FORECAST under the current reorder policy; not a "
                "certainty. If substitutes are in stock the real risk is lower.",
    }


def _quant_substitutes(db: Session, product_id=None, product=None) -> dict:
    """A product's acceptable alternatives and their current stock."""
    from app.services.quant import substitutes as subs

    pid = _resolve_product_id(db, product_id, product)
    if pid is None:
        return {"error": "product not found; give a product id, code or name"}
    av = subs.substitute_availability(db, pid)
    return {
        "product_id": pid, "substitute_count": av["substitute_count"],
        "substitutes_in_stock": av["substitutes_in_stock"],
        "total_substitute_on_hand": av["total_substitute_on_hand"],
        "substitutes": [
            {"name": s["substitute_name"], "code": s["substitute_code"],
             "on_hand": s["on_hand"], "note": s["note"],
             "preference_rank": s["preference_rank"]}
            for s in av["substitutes"]
        ],
    }


def _add_substitute(db: Session, product=None, substitute=None,
                    note: str | None = None, preference_rank: int = 1) -> dict:
    """Record that one product may be substituted by another (mutating action)."""
    from app.services.quant import substitutes as subs

    pid = _resolve_product_id(db, product=product)
    sid = _resolve_product_id(db, product=substitute)
    if pid is None or sid is None:
        return {"error": "give both the product and its substitute by code or name"}
    return subs.add_substitute(db, pid, sid, preference_rank=int(preference_rank),
                               note=note)


def _quant_reorder_plan(db: Session, service_level: float = 0.95) -> dict:
    """Portfolio-wide reorder plan: which products to order now and how much."""
    from app.services.quant import service as qsvc

    scan = qsvc.reorder_scan(db, service_level=float(service_level))
    return {
        "counts": scan["counts"],
        "total_estimated_restock_cost": scan["total_estimated_restock_cost"],
        # Cap the list so the model gets the actionable head, not the whole catalogue.
        "order_now": [
            {"product": i["product_name"], "code": i["product_code"],
             "abc_class": i.get("abc_class"),
             "quantity": i["recommended_order_quantity"],
             "estimated_cost": i["estimated_order_cost"],
             "margin_at_risk": i.get("margin_at_risk_over_horizon"),
             "pattern": i["pattern"]}
            for i in scan["items"] if i["recommendation_status"] == "READY"
        ][:20],
        "needs_review": [
            {"product": i["product_name"], "code": i["product_code"],
             "warnings": i["warnings"]}
            for i in scan["items"] if i["recommendation_status"] != "READY"
        ][:20],
        "service_level": scan["service_level"],
    }


# --------------------------------------------------------------------------- #
# Registry.
# --------------------------------------------------------------------------- #
TOOLS: list[ToolDef] = [
    ToolDef(
        "get_full_business_analysis",
        "COMPREHENSIVE one-call business analysis — use this for open-ended requests "
        "like 'analyse my business', 'how am I doing', or 'give me insights'. Returns "
        "KPIs, the 6-month P&L trend, customer and product intelligence, ABC classes, "
        "data-quality issues, AND a data_provenance block stating whether the figures "
        "are real or demo/synthetic. Synthesise it into insights and recommendations; "
        "never call demo data real.",
        {"type": "object", "properties": {}},
        _full_business_analysis, provenance="MODEL_OUTPUT", mutating=False,
        min_role=Role.VIEWER.value,
    ),
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
    ToolDef(
        "get_demand_forecast",
        "Deterministic demand forecast for one product: its demand pattern "
        "(smooth/intermittent/lumpy), the fitted model, and a predictive distribution "
        "(expected weekly demand plus p05..p95). Identify the product by id, code, or name.",
        {"type": "object", "properties": {
            "product_id": {"type": ["integer", "string"]},
            "product": {"type": "string", "description": "product code or name"},
            "horizon_periods": {"type": "integer", "minimum": 1, "maximum": 52},
        }},
        _quant_forecast, provenance="FORECAST", mutating=False, min_role=Role.VIEWER.value,
    ),
    ToolDef(
        "get_reorder_recommendation",
        "Reorder policy for one product: safety stock, order-up-to level, protection "
        "horizon and the recommended order quantity, with a forecast-quality gate. "
        "Identify the product by id, code, or name; optional service_level (0.5-0.999).",
        {"type": "object", "properties": {
            "product_id": {"type": ["integer", "string"]},
            "product": {"type": "string"},
            "service_level": {"type": "number", "minimum": 0.5, "maximum": 0.999},
        }},
        _quant_reorder, provenance="MODEL_OUTPUT", mutating=False, min_role=Role.VIEWER.value,
    ),
    ToolDef(
        "get_abc_classification",
        "ABC classification of the catalogue by annualised demand value (class A/B/C), "
        "with short-history products held out in a separate low-evidence section.",
        {"type": "object", "properties": {}},
        _quant_abc, provenance="MODEL_OUTPUT", mutating=False, min_role=Role.VIEWER.value,
    ),
    ToolDef(
        "get_reorder_plan",
        "PORTFOLIO reorder plan across the whole catalogue — use for 'what should I "
        "reorder', 'what needs restocking', or a purchase plan. Returns how many "
        "products to order now, the estimated capital to restock, the per-product "
        "quantities (largest spend first), and items whose forecast is too "
        "uncertain to auto-recommend (needs_review). Optional service_level.",
        {"type": "object", "properties": {
            "service_level": {"type": "number", "minimum": 0.5, "maximum": 0.999},
        }},
        _quant_reorder_plan, provenance="MODEL_OUTPUT", mutating=False,
        min_role=Role.VIEWER.value,
    ),
    ToolDef(
        "get_portfolio_stockout_risk",
        "Whole-catalogue stockout exposure from a portfolio Monte-Carlo: the "
        "probability that ANY product stocks out over the horizon, the expected "
        "fraction of products stocking out, portfolio fill rate and cycle service "
        "level, and the highest-risk products. Use for 'how exposed am I to "
        "stockouts', 'overall service level'. FORECAST with uncertainty.",
        {"type": "object", "properties": {
            "horizon_days": {"type": "integer", "minimum": 7, "maximum": 365},
        }},
        _quant_portfolio_risk, provenance="FORECAST", mutating=False,
        min_role=Role.VIEWER.value,
    ),
    ToolDef(
        "get_substitutes",
        "A product's acceptable alternatives (e.g. same part, different brand or "
        "origin) and how much of each is in stock now. Use for 'what can replace X', "
        "'is there an alternative to X', or when X is low. Identify the product by "
        "id, code, or name.",
        {"type": "object", "properties": {
            "product_id": {"type": ["integer", "string"]},
            "product": {"type": "string", "description": "product code or name"},
        }},
        _quant_substitutes, provenance="REAL", mutating=False,
        min_role=Role.VIEWER.value,
    ),
    ToolDef(
        "add_substitute",
        "Record that one product can be substituted by another (e.g. 'a Turkey "
        "piston can replace the China piston'). Give both products by code or name, "
        "an optional note (brand/origin) and preference rank (1 = most preferred).",
        {"type": "object", "properties": {
            "product": {"type": "string", "description": "the product being replaced"},
            "substitute": {"type": "string", "description": "the acceptable alternative"},
            "note": {"type": "string"},
            "preference_rank": {"type": "integer", "minimum": 1},
        }, "required": ["product", "substitute"]},
        _add_substitute, provenance="REAL", mutating=True, min_role=Role.STAFF.value,
    ),
    ToolDef(
        "get_activity_log",
        "Recent activity from the automatic audit trail — who changed what and when. "
        "Use for 'what happened today', 'who changed X', 'recent changes'. Optionally "
        "filter by entity_type (e.g. 'products','invoices','customers'), a product "
        "(code or name), or action ('CREATE','UPDATE','DELETE').",
        {"type": "object", "properties": {
            "entity_type": {"type": "string"},
            "product": {"type": "string", "description": "a product code or name"},
            "action": {"type": "string", "enum": ["CREATE", "UPDATE", "DELETE"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        }},
        _activity_log, provenance="REAL", mutating=False, min_role=Role.ANALYST.value,
    ),
    ToolDef(
        "get_receivables",
        "Money owed to the business (accounts receivable): total outstanding, how "
        "much is overdue, the aging breakdown (current / 1-30 / 31-60 / 61-90 / 90+ "
        "days) and the top debtors. Use for 'who owes me money', 'how much is "
        "outstanding', 'receivables'.",
        {"type": "object", "properties": {}},
        _receivables_summary, provenance="REAL", mutating=False, min_role=Role.STAFF.value,
    ),
    ToolDef(
        "get_overdue_receivables",
        "Overdue invoices — customers who are past their due date and still owe. Use "
        "for 'who is overdue', 'who should I chase for payment'.",
        {"type": "object", "properties": {}},
        _overdue_receivables, provenance="REAL", mutating=False, min_role=Role.STAFF.value,
    ),
    ToolDef(
        "get_customer_balance",
        "How much one customer owes, their credit limit and recent invoices/payments. "
        "Identify the customer by name or code.",
        {"type": "object", "properties": {
            "customer": {"type": "string", "description": "customer name or code"},
            "customer_id": {"type": ["integer", "string"]},
        }},
        _customer_balance, provenance="REAL", mutating=False, min_role=Role.STAFF.value,
    ),
    ToolDef(
        "record_payment",
        "Record a payment a customer made against an invoice. Give the invoice "
        "number, the amount, and the method (cash/transfer/pos/opay/moniepoint/etc). "
        "Rejects overpayment beyond the outstanding balance.",
        {"type": "object", "properties": {
            "invoice_number": {"type": "string"},
            "invoice_id": {"type": ["integer", "string"]},
            "amount": {"type": "number", "minimum": 0},
            "method": {"type": "string"},
            "reference": {"type": "string", "description": "bank/txn reference"},
        }, "required": ["amount"]},
        _record_payment, provenance="REAL", mutating=True, min_role=Role.STAFF.value,
    ),
    ToolDef(
        "get_payables",
        "Money the business owes suppliers (accounts payable): total owed, how much "
        "is overdue, the aging breakdown and the biggest creditors. Use for 'who do "
        "I owe', 'what do I owe suppliers', 'payables'.",
        {"type": "object", "properties": {}},
        _payables_summary, provenance="REAL", mutating=False, min_role=Role.MANAGER.value,
    ),
    ToolDef(
        "get_cash_flow",
        "Cash flow: money in vs money out over a recent window (default 30 days), the "
        "net, and outstanding balances — what's owed to us (receivables) vs what we "
        "owe (payables), and the net position. Use for 'how is my cash', 'cash flow', "
        "'am I collecting more than I'm spending'.",
        {"type": "object", "properties": {
            "days": {"type": "integer", "minimum": 1, "maximum": 365},
        }},
        _cash_flow, provenance="REAL", mutating=False, min_role=Role.MANAGER.value,
    ),
    ToolDef(
        "get_landed_cost",
        "Estimated landed cost of a product — the supplier's base cost plus import "
        "uplifts (freight, duty, levies, clearing, FX buffer). Identify the product "
        "by id, code, or name. IMPORTANT: if 'configured' is false the uplifts are "
        "PLACEHOLDERS, not real figures — say so and do not present the landed cost "
        "as accurate.",
        {"type": "object", "properties": {
            "product_id": {"type": ["integer", "string"]},
            "product": {"type": "string", "description": "product code or name"},
        }},
        _quant_landed_cost, provenance="ASSUMPTION", mutating=False,
        min_role=Role.VIEWER.value,
    ),
    ToolDef(
        "get_supplier_scores",
        "Risk-adjusted supplier scores (0-1, higher is better) and supplier risk, "
        "built from configured reliability and realised lead-time consistency and "
        "length. Use for 'which supplier is most reliable', 'who should I buy from', "
        "or supplier-comparison questions. Weights are stated assumptions.",
        {"type": "object", "properties": {}},
        _quant_supplier_scores, provenance="MODEL_OUTPUT", mutating=False,
        min_role=Role.VIEWER.value,
    ),
    ToolDef(
        "get_budget_reorder_plan",
        "Budget-constrained purchase plan — use when the user gives a restock "
        "budget ('I have ₦2m to restock, what should I buy'). Allocates the budget "
        "to protect the most gross margin at risk: returns what to buy (product, "
        "quantity, cost), total spend, margin protected, and what was skipped for "
        "lack of budget. Deterministic priority allocation, not a claim of optimality.",
        {"type": "object", "properties": {
            "budget": {"type": "number", "minimum": 0,
                       "description": "restock budget in Naira"},
            "service_level": {"type": "number", "minimum": 0.5, "maximum": 0.999},
        }, "required": ["budget"]},
        _quant_budget_plan, provenance="MODEL_OUTPUT", mutating=False,
        min_role=Role.VIEWER.value,
    ),
    ToolDef(
        "get_stockout_risk",
        "Simulated stockout risk for one product — runs a daily Monte-Carlo of the "
        "reorder policy and returns the probability of a stockout, expected fill "
        "rate, cycle service level, expected lost units and the stockout cost "
        "(lost margin). Use for 'will I run out of X', 'how safe is my stock of X', "
        "or service-level questions. Identify the product by id, code, or name; "
        "these are FORECASTS with uncertainty.",
        {"type": "object", "properties": {
            "product_id": {"type": ["integer", "string"]},
            "product": {"type": "string", "description": "product code or name"},
            "horizon_days": {"type": "integer", "minimum": 7, "maximum": 365},
        }},
        _quant_stockout_risk, provenance="FORECAST", mutating=False,
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
