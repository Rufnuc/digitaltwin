"""Product substitutes — acceptable alternatives (e.g. same part, different brand/
origin) and their live availability (Phase 2 follow-up).

The value for the intelligence layer: when a part is at risk of running out, an
in-stock substitute changes the picture — you may not need to panic-order. These
functions list a product's substitutes with their current on-hand stock so the
reorder/stockout tools can say "X may run out, but alternative Y has N in stock".
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.product import Product, ProductSubstitute
from app.models.warehouse import StockLot


def _on_hand(db: Session, product_id: int) -> int:
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


def list_substitutes(db: Session, product_id: int) -> list[dict]:
    """A product's substitutes (best preference first) with live on-hand stock."""
    rows = db.execute(
        select(ProductSubstitute, Product)
        .join(Product, Product.id == ProductSubstitute.substitute_id)
        .where(ProductSubstitute.product_id == product_id)
        .order_by(ProductSubstitute.preference_rank, ProductSubstitute.id)
    ).all()
    out = []
    for sub, prod in rows:
        out.append({
            "substitute_id": prod.id, "substitute_code": prod.code,
            "substitute_name": prod.name, "preference_rank": sub.preference_rank,
            "note": sub.note, "on_hand": _on_hand(db, prod.id),
            "selling_price": float(prod.selling_price) if prod.selling_price else None,
        })
    return out


def substitute_availability(db: Session, product_id: int) -> dict:
    """Summary used by the reorder/stockout tools: how much cover the substitutes
    provide right now."""
    subs = list_substitutes(db, product_id)
    total_alt = sum(s["on_hand"] for s in subs)
    in_stock = [s for s in subs if s["on_hand"] > 0]
    return {
        "product_id": product_id,
        "substitute_count": len(subs),
        "substitutes_in_stock": len(in_stock),
        "total_substitute_on_hand": total_alt,
        "has_cover": total_alt > 0,
        "substitutes": subs,
    }


def add_substitute(db: Session, product_id: int, substitute_id: int,
                   preference_rank: int = 1, note: str | None = None) -> dict:
    """Record that `substitute_id` may serve `product_id`. Idempotent per pair."""
    if product_id == substitute_id:
        return {"status": "ERROR", "error": "a product cannot substitute itself"}
    for pid in (product_id, substitute_id):
        if db.get(Product, pid) is None:
            return {"status": "ERROR", "error": f"product {pid} not found"}
    existing = db.scalar(
        select(ProductSubstitute).where(
            ProductSubstitute.product_id == product_id,
            ProductSubstitute.substitute_id == substitute_id,
        )
    )
    if existing:
        existing.preference_rank = preference_rank
        existing.note = note
    else:
        db.add(ProductSubstitute(product_id=product_id, substitute_id=substitute_id,
                                 preference_rank=preference_rank, note=note,
                                 data_origin="REAL"))
    db.commit()
    return {"status": "OK", "product_id": product_id, "substitute_id": substitute_id}


def remove_substitute(db: Session, product_id: int, substitute_id: int) -> dict:
    row = db.scalar(
        select(ProductSubstitute).where(
            ProductSubstitute.product_id == product_id,
            ProductSubstitute.substitute_id == substitute_id,
        )
    )
    if row is None:
        return {"status": "NOT_FOUND"}
    db.delete(row)
    db.commit()
    return {"status": "OK"}
