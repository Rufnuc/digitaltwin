"""News → business-impact engine (spec §31).

Turns a REAL market signal into a quantified, clearly-labelled impact:

    FACT (observed data)  →  ASSUMPTION (mapping + magnitude)
      →  POSSIBLE IMPACT (affected suppliers/products/costs/customers)
      →  SIMULATION (deterministic engine)  →  RISK  →  RECOMMENDED ACTION

Possibility is never confused with certainty: the observed indicator is REAL, the
mapping to a scenario lever is an ASSUMPTION, and the numbers are MODEL_OUTPUT from
the same simulation engine used elsewhere. Nothing here is invented.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AlertSeverity, DataOrigin
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.system import Alert
from app.services.analytics import baseline_economics
from app.services.market_intelligence.ingest import latest_indicators
from app.services.simulation.model import REPORT_METRICS, Levers, project

# Impact is "material" when it moves net profit by at least this fraction.
MATERIAL_THRESHOLD = 0.05

DEFAULT_ASSUMPTIONS = {
    "cost_passthrough": 0.4,   # fraction of inflation that flows into unit costs
    "fx_shock_pct": 10.0,      # assumed further NGN depreciation to stress-test
    "import_share": 0.6,       # fraction of COGS that is import-linked
}


def _import_suppliers(db: Session) -> list[dict]:
    rows = db.scalars(
        select(Supplier).where(Supplier.location.ilike("Import%"))
    ).all()
    return [{"id": s.id, "name": s.name, "location": s.location} for s in rows]


def _products_from(db: Session, supplier_ids: list[int]) -> int:
    if not supplier_ids:
        return 0
    return int(
        db.scalar(
            select(func.count(Product.id)).where(Product.supplier_id.in_(supplier_ids))
        ) or 0
    )


def _simulate(db: Session, levers: Levers) -> dict:
    baseline = baseline_economics(db)
    base = project(baseline, Levers())
    scen = project(baseline, levers)
    results = []
    for m in REPORT_METRICS:
        b, s = base.metric(m), scen.metric(m)
        pct = ((s - b) / b * 100.0) if b else 0.0
        rnd = 4 if m == "gross_margin" else 2
        results.append({
            "metric": m, "baseline": round(b, rnd), "scenario": round(s, rnd),
            "change_percent": round(pct, 2),
        })
    net = next(r for r in results if r["metric"] == "net_profit")
    return {"results": results, "net_profit_change_percent": net["change_percent"],
            "model_name": "general_pnl_deterministic", "model_version": "1.0.0"}


def _indicator(db: Session, key: str) -> dict | None:
    for i in latest_indicators(db):
        if i["indicator"] == key:
            return i
    return None


def assess_inflation(db: Session, assumptions: dict) -> dict | None:
    fact = _indicator(db, "inflation_cpi_yoy")
    if not fact:
        return None
    passthrough = float(
        assumptions.get("cost_passthrough", DEFAULT_ASSUMPTIONS["cost_passthrough"])
    )
    unit_cost_pct = round(fact["value"] * passthrough, 2)
    sim = _simulate(db, Levers(unit_cost_pct=unit_cost_pct))
    return {
        "driver": "inflation",
        "title": "Inflation cost pressure",
        "fact": fact,
        "assumptions": {
            "cost_passthrough": passthrough,
            "derived_unit_cost_change_percent": unit_cost_pct,
            "note": "Assumes a fraction of the observed inflation rate flows into unit costs "
                    "over the horizon. Elasticity/price response not modelled here.",
        },
        "possible_impact": {
            "costs": "All product unit costs rise with general inflation.",
            "products": "Margins compress across the catalogue unless prices are raised.",
            "customers": "Price increases to protect margin may dampen demand.",
        },
        "lever": {"field": "unit_cost_change_percent", "value": unit_cost_pct},
        "simulation": sim,
        "risk": "Sustained high inflation erodes gross margin if prices lag costs.",
        "recommended_action": "Review selling prices; run a price-change simulation to find the "
                              "increase that restores margin without losing volume.",
        "provenance": {"fact": DataOrigin.REAL.value, "mapping": DataOrigin.ASSUMPTION.value,
                       "numbers": DataOrigin.MODEL_OUTPUT.value},
    }


def assess_fx(db: Session, assumptions: dict) -> dict | None:
    # Prefer CNY — most imported parts are sourced from China — then USD.
    fact = (_indicator(db, "fx_cny_ngn") or _indicator(db, "fx_usd_ngn")
            or _indicator(db, "official_fx_usd"))
    if not fact:
        return None
    shock = float(assumptions.get("fx_shock_pct", DEFAULT_ASSUMPTIONS["fx_shock_pct"]))
    import_share = float(assumptions.get("import_share", DEFAULT_ASSUMPTIONS["import_share"]))
    unit_cost_pct = round(shock * import_share, 2)
    sim = _simulate(db, Levers(unit_cost_pct=unit_cost_pct))

    suppliers = _import_suppliers(db)
    affected_products = _products_from(db, [s["id"] for s in suppliers])
    return {
        "driver": "fx",
        "title": "Naira depreciation / import-cost exposure",
        "fact": fact,
        "assumptions": {
            "fx_shock_pct": shock,
            "import_share": import_share,
            "derived_unit_cost_change_percent": unit_cost_pct,
            "note": "Stress-tests a further naira depreciation applied to the import-linked share "
                    "of COGS. The current exchange rate is the observed FACT.",
        },
        "possible_impact": {
            "suppliers": suppliers,
            "products": f"{affected_products} products sourced from import suppliers.",
            "costs": "Import-linked unit costs rise as the naira weakens.",
        },
        "lever": {"field": "unit_cost_change_percent", "value": unit_cost_pct},
        "simulation": sim,
        "risk": "FX volatility raises landed cost of imported parts and squeezes margin.",
        "recommended_action": "Consider forward cover, local sourcing, or price adjustments; "
                              "simulate a supplier-cost-change scenario to size the effect.",
        "provenance": {"fact": DataOrigin.REAL.value, "mapping": DataOrigin.ASSUMPTION.value,
                       "numbers": DataOrigin.MODEL_OUTPUT.value},
    }


ASSESSORS = {"inflation": assess_inflation, "fx": assess_fx}


def _maybe_alert(db: Session, assessment: dict) -> bool:
    change = assessment["simulation"]["net_profit_change_percent"]
    if abs(change) < MATERIAL_THRESHOLD * 100:
        return False
    db.add(Alert(
        severity=AlertSeverity.HIGH.value if abs(change) >= 15 else AlertSeverity.MEDIUM.value,
        category="market_impact",
        title=f"{assessment['title']}: net profit could move {change:+.1f}%",
        body=f"{assessment['risk']} Recommended: {assessment['recommended_action']}",
        # Derived from a model + assumptions off real data — not an observed fact.
        data_origin=DataOrigin.MODEL_OUTPUT.value,
    ))
    return True


def scan(db: Session, assumptions: dict | None = None, create_alerts: bool = True) -> dict:
    assumptions = {**DEFAULT_ASSUMPTIONS, **(assumptions or {})}
    assessments = []
    alerts_created = 0
    for fn in ASSESSORS.values():
        a = fn(db, assumptions)
        if a is None:
            continue
        change = a["simulation"]["net_profit_change_percent"]
        a["materiality"] = {
            "net_profit_change_percent": change,
            "material": abs(change) >= MATERIAL_THRESHOLD * 100,
        }
        assessments.append(a)
        if create_alerts and _maybe_alert(db, a):
            alerts_created += 1
    if create_alerts:
        db.commit()
    return {
        "assessments": assessments,
        "alerts_created": alerts_created,
        "has_market_data": bool(assessments),
        "note": "FACT is observed real data; the mapping to a scenario is an ASSUMPTION; the "
                "numbers are deterministic MODEL OUTPUTS — a possibility, not a certainty.",
    }
