"""Supplier scoring and landed cost (spec v4 §6 supplier risk, §9 landed cost; Phase 2).

Supplier score is a transparent composite of REAL signals only — configured
reliability (or an on-time rate derived from realised receipts) and realised
lead-time mean/variability. Weights are stated ASSUMPTIONS; components that have no
evidence are excluded, not invented, and the score renormalises over what is known.

Landed cost is the pure §9 decomposition. Freight/duty/handling/FX/quality are used
only when explicitly provided; otherwise they stay null and a warning is returned —
the app has no source for them yet, so landed cost equals the base unit cost.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import DataOrigin
from app.models.purchase import Purchase
from app.models.supplier import Supplier
from app.models.warehouse import StockLot
from app.services.quant import leadtime as lt

# Composite weights (ASSUMPTION): reliability matters most, then lead-time
# consistency, then how short the lead is.
W_RELIABILITY = 0.5
W_CONSISTENCY = 0.3   # 1 - lead_time_risk
W_LEAD_LENGTH = 0.2
LEAD_REF_DAYS = 90.0  # reference lead for the length score (import business)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def landed_cost(
    base_unit_cost: float | None, *, freight: float | None = None,
    duty: float | None = None, handling: float | None = None,
    fx_surcharge: float | None = None, quality: float | None = None,
) -> dict:
    """§9 landed-cost decomposition. Only provided components are summed; missing
    ones stay null and are reported, so the total is never silently understated."""
    components = {"base_unit_cost": base_unit_cost, "freight_per_unit": freight,
                  "duty_per_unit": duty, "handling_per_unit": handling,
                  "fx_risk_surcharge_per_unit": fx_surcharge,
                  "expected_quality_cost_per_unit": quality}
    missing = [k for k, v in components.items() if v is None and k != "base_unit_cost"]
    if base_unit_cost is None:
        return {"status": "INSUFFICIENT_DATA", "components": components,
                "total_landed_cost": None, "missing_components": missing,
                "warnings": ["MISSING_BASE_COST"]}
    total = round(sum(v for v in components.values() if v is not None), 4)
    warnings = ["LANDED_COST_COMPONENTS_MISSING"] if missing else []
    return {"status": "OK", "components": components, "total_landed_cost": total,
            "missing_components": missing, "warnings": warnings,
            "provenance": "REAL" if not missing else "PARTIAL"}


def supplier_lead_times(db: Session, supplier_id: int,
                        include_demo: bool = False) -> list[float]:
    """Realised lead days for a supplier's receipts (purchase_date → received_date)."""
    stmt = (
        select(Purchase.purchase_date, StockLot.received_date)
        .join(Purchase, Purchase.id == StockLot.purchase_id)
        .where(StockLot.supplier_id == supplier_id, StockLot.purchase_id.is_not(None))
    )
    if not include_demo:
        stmt = stmt.where(StockLot.data_origin != DataOrigin.DEMO.value)
    out: list[float] = []
    for ordered, received in db.execute(stmt).all():
        if ordered is not None and received is not None:
            days = (received - ordered).days
            if days >= 0:
                out.append(float(days))
    return out


def _on_time_rate(samples: list[float], promised_days: float | None) -> float | None:
    """Fraction of receipts that arrived within the promised lead time."""
    if not samples or promised_days is None:
        return None
    on_time = sum(1 for s in samples if s <= promised_days + 1e-9)
    return round(on_time / len(samples), 4)


def score_supplier(db: Session, supplier: Supplier, include_demo: bool = False) -> dict:
    """Risk-adjusted score in [0,1] from real signals, with a component breakdown."""
    samples = supplier_lead_times(db, supplier.id, include_demo=include_demo)
    lt_stats = lt.lead_time_stats(samples, point_estimate=supplier.lead_time_days)

    # Reliability: configured score if present, else the realised on-time rate.
    reliability = supplier.reliability_score
    reliability_source = "CONFIGURED"
    if reliability is None:
        reliability = _on_time_rate(samples, supplier.lead_time_days)
        reliability_source = "DERIVED_ON_TIME" if reliability is not None else "NONE"

    lead_risk = lt_stats.get("lead_time_risk")           # 0..1, higher = more variable
    mean_lead = lt_stats.get("mean_days")

    # Build the composite over available components only, then renormalise.
    parts: list[tuple[float, float]] = []  # (weight, value in [0,1])
    if reliability is not None:
        parts.append((W_RELIABILITY, _clamp01(float(reliability))))
    if lead_risk is not None:
        parts.append((W_CONSISTENCY, _clamp01(1.0 - float(lead_risk))))
    if mean_lead is not None:
        parts.append((W_LEAD_LENGTH, _clamp01(1.0 - float(mean_lead) / LEAD_REF_DAYS)))

    if parts:
        wsum = sum(w for w, _ in parts)
        score = round(sum(w * v for w, v in parts) / wsum, 4)
        status = "OK"
    else:
        score = None
        status = "INSUFFICIENT_DATA"

    return {
        "supplier_id": supplier.id, "supplier_code": supplier.code,
        "supplier_name": supplier.name, "currency": supplier.currency,
        "status": status,
        "score": score,
        "supplier_risk": round(1.0 - score, 4) if score is not None else None,
        "components": {
            "reliability": None if reliability is None else round(float(reliability), 4),
            "reliability_source": reliability_source,
            "lead_time_mean_days": mean_lead,
            "lead_time_std_days": lt_stats.get("std_days"),
            "lead_time_risk": lead_risk,
            "lead_time_source": lt_stats.get("source"),
            "receipts_observed": len(samples),
        },
        "weights": {"reliability": W_RELIABILITY, "consistency": W_CONSISTENCY,
                    "lead_length": W_LEAD_LENGTH, "note": "ASSUMPTION"},
        "provenance": "MODEL_OUTPUT",
    }
