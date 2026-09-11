"""Product intelligence (spec §25)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.invoice import InvoiceLine
from app.models.product import Product


def product_metrics(db: Session) -> list[dict]:
    stmt = (
        select(
            Product.id,
            Product.code,
            Product.name,
            Product.category,
            func.coalesce(func.sum(InvoiceLine.line_total), 0),
            func.coalesce(func.sum(InvoiceLine.quantity), 0),
            func.coalesce(func.sum(InvoiceLine.quantity * InvoiceLine.unit_cost), 0),
        )
        .select_from(Product)
        .join(InvoiceLine, InvoiceLine.product_id == Product.id, isouter=True)
        .group_by(Product.id, Product.code, Product.name, Product.category)
    )
    out: list[dict] = []
    for pid, code, name, category, revenue, units, cogs in db.execute(stmt).all():
        revenue = float(revenue or 0)
        cogs = float(cogs or 0)
        gross = revenue - cogs
        out.append(
            {
                "product_id": pid,
                "code": code,
                "name": name,
                "category": category,
                "revenue": round(revenue, 2),
                "units": float(units or 0),
                "gross_profit": round(gross, 2),
                "gross_margin": round(gross / revenue, 4) if revenue else 0.0,
            }
        )
    return out


def product_intelligence(db: Session, top_n: int = 10) -> dict:
    metrics = product_metrics(db)
    sold = [m for m in metrics if m["units"] > 0]

    # Dead stock: on-hand quantity but no sales in the dataset (spec §25).
    on_hand = {
        pid: qty
        for pid, qty in db.execute(
            select(Inventory.product_id, func.sum(Inventory.quantity_on_hand)).group_by(
                Inventory.product_id
            )
        ).all()
    }
    dead_stock = [
        {**m, "on_hand": int(on_hand.get(m["product_id"], 0) or 0)}
        for m in metrics
        if m["units"] == 0 and (on_hand.get(m["product_id"], 0) or 0) > 0
    ]

    by_revenue = sorted(sold, key=lambda m: m["revenue"], reverse=True)
    by_margin = sorted(sold, key=lambda m: m["gross_margin"], reverse=True)
    slow_movers = sorted(sold, key=lambda m: m["units"])[:top_n]

    return {
        "summary": {
            "products_sold": len(sold),
            "dead_stock_count": len(dead_stock),
        },
        "best_sellers": by_revenue[:top_n],
        "most_profitable": by_margin[:top_n],
        "slow_movers": slow_movers,
        "dead_stock": dead_stock[:top_n],
        "provenance": "MODEL_OUTPUT",
    }
