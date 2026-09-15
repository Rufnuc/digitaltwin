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
                    service_level: float = ro.DEFAULT_SERVICE_LEVEL,
                    review_period_days: int = 7, include_demo: bool = False) -> dict:
    prod = db.get(Product, product_id)
    if prod is None:
        return {"status": "NOT_FOUND", "product_id": product_id}
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

    rec = ro.reorder_recommendation(
        weekly_mean=weekly_mean, weekly_std=weekly_std,
        inventory_position=_on_hand(db, product_id),
        mean_lead_time_days=float(lead), review_period_days=review_period_days,
        service_level=service_level, unit_cost=float(prod.purchase_cost),
        uncertainty_ratio=_uncertainty_ratio(forecast),
        wape=diagnostics.get("wape"), validation_status=diagnostics.get("validation_status"),
        moq=1.0, order_multiple=float(prod.reorder_quantity or 1) if prod.reorder_quantity else 1.0,
    )
    eoq = ro.eoq(
        annual_demand_units=round(weekly_mean * 52, 4),
        ordering_cost=None, unit_cost=float(prod.purchase_cost),
    )
    return {
        "status": "OK",
        "product_id": product_id,
        "product_code": prod.code,
        "product_name": prod.name,
        "pattern": pattern["pattern"],
        "recommendation": rec,
        "eoq": eoq,
        "diagnostics": diagnostics,
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
