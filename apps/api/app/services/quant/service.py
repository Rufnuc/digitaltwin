"""Composition layer: demand -> classification -> forecast -> reorder per product.

Pulls real inputs from the repository (verified sales, product cost/lead time,
on-hand from stock lots with a legacy-inventory fallback) and returns structured,
provenance-tagged quant results. No numbers are invented; missing inputs surface
as explicit statuses/warnings (spec v4 §11).
"""
from __future__ import annotations

import statistics
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.product import Product
from app.models.warehouse import StockLot
from app.services.quant import backtest as bt
from app.services.quant import bridge as br
from app.services.quant import classification as cls
from app.services.quant import config_version
from app.services.quant import demand as dmd
from app.services.quant import forecast as fc
from app.services.quant import leadtime as lt
from app.services.quant import reorder as ro


def _on_hand(db: Session, product_id: int) -> int:
    """Total on-hand: lot-based if any lots exist, else the legacy inventory table."""
    lot_qty = db.scalar(
        select(func.coalesce(func.sum(StockLot.quantity_remaining), 0))
        .where(StockLot.product_id == product_id)
    )
    if lot_qty and lot_qty > 0:
        return int(lot_qty)
    legacy = db.scalar(
        select(func.coalesce(func.sum(Inventory.quantity_on_hand), 0))
        .where(Inventory.product_id == product_id)
    )
    return int(legacy or 0)


def _weekly_stats(units: list[float]) -> tuple[float, float]:
    if not units:
        return 0.0, 0.0
    mean = statistics.fmean(units)
    std = statistics.pstdev(units) if len(units) > 1 else 0.0
    return mean, std


def service_level_for_class(abc_class: str | None) -> float:
    """ABC-aware cycle service level: A items are protected more than C (config)."""
    from app.core.config import settings
    return {
        "A": settings.QUANT_SERVICE_LEVEL_A,
        "B": settings.QUANT_SERVICE_LEVEL_B,
        "C": settings.QUANT_SERVICE_LEVEL_C,
    }.get(abc_class, settings.QUANT_SERVICE_LEVEL_DEFAULT)


def _abc_class_map(db: Session, as_of: date | None = None,
                   include_demo: bool = False) -> dict[int, str]:
    """product_id -> ABC class ('A'/'B'/'C') across the active catalogue."""
    report = abc_report(db, as_of=as_of, include_demo=include_demo)
    return {i["product_id"]: i["abc_class"] for i in report.get("items", [])}


def _uncertainty_ratio(forecast: dict) -> float | None:
    q = forecast.get("quantiles") or {}
    if not q.get("p50"):
        return None
    p05, p50, p95 = q["p05"][0], q["p50"][0], q["p95"][0]
    return round((p95 - p05) / max(p50, 1.0), 6)


def product_forecast(db: Session, product_id: int, as_of: date | None = None,
                     horizon: int = 12, seed: int = 42, include_demo: bool = False) -> dict:
    prod = db.get(Product, product_id)
    if prod is None:
        return {"status": "NOT_FOUND", "product_id": product_id}
    series = dmd.product_weekly_demand(db, product_id, as_of, include_demo=include_demo)
    pattern = cls.classify_pattern(series["units"])
    forecast = fc.forecast(series["units"], pattern["pattern"], horizon=horizon, seed=seed)
    diagnostics = bt.rolling_origin_backtest(series["units"], pattern["pattern"], seed=seed)
    # Weekly→daily bridge for the next-period expected value (feeds the daily
    # inventory-policy simulation in Phase 2).
    e_week = (forecast.get("quantiles", {}).get("p50") or [0.0])[0]
    events = br.product_daily_events(db, product_id, as_of, include_demo=include_demo)
    bridge = br.daily_bridge(e_week, events, date.fromisoformat(series["as_of"]))
    return {
        "status": "OK" if pattern["pattern"] != "NO_EVIDENCE" else "INSUFFICIENT_DATA",
        "product_id": product_id,
        "product_code": prod.code,
        "product_name": prod.name,
        "as_of": series["as_of"],
        "demand": {"weeks_observed": len(series["units"]),
                   "total_units": series["total_units"], "stats": series["stats"]},
        "classification": pattern,
        "forecast": forecast,
        "daily_bridge": bridge,
        "diagnostics": diagnostics,
        "config_version": config_version(),
        "provenance": "MODEL_OUTPUT",
    }


def product_reorder(db: Session, product_id: int, as_of: date | None = None,
                    service_level: float | None = None,
                    review_period_days: int = 7, include_demo: bool = False,
                    abc_class: str | None = None) -> dict:
    """Reorder recommendation. If ``service_level`` is None it is derived from the
    product's ABC class (A items protected more) — the ABC-aware default. Pass
    ``abc_class`` to avoid recomputing the classification (used by reorder_scan)."""
    prod = db.get(Product, product_id)
    if prod is None:
        return {"status": "NOT_FOUND", "product_id": product_id}
    # ABC-aware service level unless the caller pinned one explicitly.
    if service_level is None:
        if abc_class is None:
            abc_class = _abc_class_map(db, as_of, include_demo).get(product_id)
        service_level = service_level_for_class(abc_class)
    series = dmd.product_weekly_demand(db, product_id, as_of, include_demo=include_demo)
    pattern = cls.classify_pattern(series["units"])
    forecast = fc.forecast(series["units"], pattern["pattern"], horizon=12)
    diagnostics = bt.rolling_origin_backtest(series["units"], pattern["pattern"])
    weekly_mean, weekly_std = _weekly_stats(series["units"])

    missing = []
    if prod.purchase_cost is None:
        missing.append("unit_cost")
    lead = prod.lead_time_days
    if lead is None:
        missing.append("lead_time_days")
    if missing:
        return {"status": "INSUFFICIENT_DATA", "product_id": product_id,
                "product_name": prod.name, "missing_fields": missing,
                "warnings": ["MISSING_INPUTS"]}

    # Lead-time statistics from realised receipts; the point estimate on the
    # product is the fallback when there is not enough receipt history.
    lt_stats = lt.product_lead_time_stats(
        db, product_id, point_estimate=float(lead), include_demo=include_demo
    )
    mean_lead = lt_stats["mean_days"] if lt_stats["mean_days"] is not None else float(lead)
    std_lead = lt_stats["std_days"] or 0.0

    rec = ro.reorder_recommendation(
        weekly_mean=weekly_mean, weekly_std=weekly_std,
        inventory_position=_on_hand(db, product_id),
        mean_lead_time_days=float(mean_lead), review_period_days=review_period_days,
        service_level=service_level, unit_cost=float(prod.purchase_cost),
        uncertainty_ratio=_uncertainty_ratio(forecast),
        wape=diagnostics.get("wape"), validation_status=diagnostics.get("validation_status"),
        moq=1.0, order_multiple=float(prod.reorder_quantity or 1) if prod.reorder_quantity else 1.0,
        std_lead_time_days=float(std_lead),
    )
    eoq = ro.eoq(
        annual_demand_units=round(weekly_mean * 52, 4),
        ordering_cost=None, unit_cost=float(prod.purchase_cost),
    )
    # Priority: gross margin exposed if we stock out over the protection horizon —
    # expected demand over the horizon × unit margin (spec v4 §6 stockout_cost
    # proxy, closed-form; the simulated version arrives with Phase 2). This lets
    # the reorder plan rank by money at risk, not just capital to spend.
    unit_margin = None
    if prod.selling_price is not None and prod.purchase_cost is not None:
        unit_margin = max(0.0, float(prod.selling_price) - float(prod.purchase_cost))
    priority_score = (
        round(rec["expected_demand_over_horizon"] * unit_margin, 2)
        if unit_margin is not None else None
    )
    return {
        "status": "OK",
        "product_id": product_id,
        "product_code": prod.code,
        "product_name": prod.name,
        "pattern": pattern["pattern"],
        "abc_class": abc_class,
        "applied_service_level": service_level,
        "unit_margin": unit_margin,
        "margin_at_risk_over_horizon": priority_score,
        "recommendation": rec,
        "lead_time": lt_stats,
        "eoq": eoq,
        "diagnostics": diagnostics,
        "config_version": config_version(),
        "provenance": "MODEL_OUTPUT",
    }


def reorder_scan(db: Session, as_of: date | None = None,
                 service_level: float | None = None,
                 include_demo: bool = False, limit: int | None = None) -> dict:
    """Portfolio reorder: run the reorder engine across active products and return
    the ones that need ordering now. This is the quant "brain" the intelligence
    surfaces (Suggestions, Benfieg) consume — every number is deterministic and
    provenance-tagged. Items are split into READY (act now) and REVIEW_REQUIRED
    (forecast quality gate tripped), and ranked by estimated capital to restock.

    Service level is ABC-aware by default (A items protected more); pass an explicit
    ``service_level`` to override for all products.
    """
    products = db.scalars(select(Product).where(Product.is_active.is_(True))).all()
    # Classify once so per-product reorder doesn't recompute the whole catalogue.
    class_map = _abc_class_map(db, as_of, include_demo) if service_level is None else {}
    items: list[dict] = []
    skipped_missing = 0
    for p in products:
        r = product_reorder(db, p.id, as_of=as_of, service_level=service_level,
                            include_demo=include_demo, abc_class=class_map.get(p.id))
        if r.get("status") != "OK":
            if r.get("status") == "INSUFFICIENT_DATA":
                skipped_missing += 1
            continue
        rec = r["recommendation"]
        qty = rec.get("recommended_order_quantity") or 0
        if qty <= 0:
            continue
        items.append({
            "product_id": r["product_id"], "product_code": r["product_code"],
            "product_name": r["product_name"], "pattern": r.get("pattern"),
            "abc_class": r.get("abc_class"),
            "applied_service_level": r.get("applied_service_level"),
            "recommended_order_quantity": qty,
            "order_up_to_level": rec.get("order_up_to_level"),
            "inventory_position": rec.get("inventory_position"),
            "safety_stock": rec.get("safety_stock"),
            "estimated_order_cost": rec.get("estimated_order_cost"),
            "margin_at_risk_over_horizon": r.get("margin_at_risk_over_horizon"),
            "recommendation_status": rec.get("recommendation_status"),
            "warnings": rec.get("warnings", []),
            "lead_time_source": r.get("lead_time", {}).get("source"),
        })

    # Rank by margin at risk if we stock out (money at stake), then by capital as a
    # tie-break; Nones last. This is the business-priority order, not just spend.
    items.sort(key=lambda i: (i["margin_at_risk_over_horizon"] or 0.0,
                              i["estimated_order_cost"] or 0.0), reverse=True)
    if limit:
        items = items[:limit]
    ready = [i for i in items if i["recommendation_status"] == "READY"]
    review = [i for i in items if i["recommendation_status"] != "READY"]
    total_cost = round(sum(i["estimated_order_cost"] or 0.0 for i in ready), 2)
    return {
        "status": "OK",
        "as_of": (as_of or date.today()).isoformat(),
        "counts": {"to_order_now": len(ready), "needs_review": len(review),
                   "insufficient_data": skipped_missing},
        "total_estimated_restock_cost": total_cost,
        "items": items,
        "service_level": service_level,
        "config_version": config_version(),
        "provenance": "MODEL_OUTPUT",
    }


def abc_report(db: Session, as_of: date | None = None, include_demo: bool = False) -> dict:
    as_of = as_of or date.today()
    products = db.scalars(select(Product).where(Product.is_active.is_(True))).all()
    rows = []
    for p in products:
        series = dmd.product_weekly_demand(db, p.id, as_of, include_demo=include_demo)
        weeks = series["units"]
        covered_days = len(weeks) * 7
        annual_units = (series["total_units"] / covered_days * 365) if covered_days else 0.0
        value = annual_units * float(p.purchase_cost) if p.purchase_cost else None
        rows.append({"product_id": p.id, "annual_demand_value": value,
                     "covered_days": covered_days})
    report = cls.classify_abc(rows)
    return {"status": "OK", "as_of": as_of.isoformat(), **report,
            "config_version": config_version(), "provenance": "MODEL_OUTPUT"}
