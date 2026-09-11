"""Supplier analytics (spec §9, §27 foundation)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.purchase import Purchase, PurchaseLine
from app.models.supplier import Supplier


def supplier_intelligence(db: Session) -> dict:
    # Spend per supplier (from purchases).
    spend = {
        sid: float(total or 0)
        for sid, total in db.execute(
            select(Purchase.supplier_id, func.sum(PurchaseLine.line_total))
            .join(PurchaseLine, PurchaseLine.purchase_id == Purchase.id)
            .group_by(Purchase.supplier_id)
        ).all()
    }
    # Product count per supplier.
    prod_counts = {
        sid: int(c or 0)
        for sid, c in db.execute(
            select(Product.supplier_id, func.count(Product.id)).group_by(Product.supplier_id)
        ).all()
    }

    rows: list[dict] = []
    for s in db.scalars(select(Supplier)).all():
        rows.append(
            {
                "supplier_id": s.id,
                "code": s.code,
                "name": s.name,
                "product_count": prod_counts.get(s.id, 0),
                "spend": round(spend.get(s.id, 0.0), 2),
                "lead_time_days": s.lead_time_days,
                "reliability_score": s.reliability_score,
                # A simple, transparent concentration signal for later risk sims.
                "single_source_products": prod_counts.get(s.id, 0),
            }
        )
    rows.sort(key=lambda r: r["spend"], reverse=True)
    total_spend = round(sum(r["spend"] for r in rows), 2)
    return {
        "summary": {"supplier_count": len(rows), "total_spend": total_spend},
        "suppliers": rows,
        "provenance": "MODEL_OUTPUT",
    }
