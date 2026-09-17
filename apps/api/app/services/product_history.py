"""A product's full history as one timeline — stock movements (receipts, sales,
transfers, adjustments) and price changes — for the product modal.

Everything is REAL recorded data; the frontend searches/filters/sorts it.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.product import ProductPriceHistory
from app.models.user import User
from app.models.warehouse import StockMovement, Warehouse


def _names(db: Session, model, ids: set[int], label_col: str) -> dict[int, str]:
    if not ids:
        return {}
    col = getattr(model, label_col)
    return {i: v for i, v in db.execute(
        select(model.id, col).where(model.id.in_(ids))).all()}


def product_history(db: Session, product_id: int, limit: int = 500) -> dict:
    """Combined, newest-first timeline of everything that happened to a product."""
    moves = db.scalars(
        select(StockMovement).where(StockMovement.product_id == product_id)
        .order_by(StockMovement.occurred_at.desc()).limit(limit)
    ).all()
    prices = db.scalars(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product_id)
        .order_by(ProductPriceHistory.effective_date.desc()).limit(limit)
    ).all()

    wh = _names(db, Warehouse, {m.warehouse_id for m in moves if m.warehouse_id}, "name")
    users = {uid: (n or e) for uid, n, e in db.execute(
        select(User.id, User.full_name, User.email)
        .where(User.id.in_({m.user_id for m in moves if m.user_id}))).all()}
    custs = _names(db, Customer, {m.customer_id for m in moves if m.customer_id}, "name")
    invs = _names(db, Invoice, {m.invoice_id for m in moves if m.invoice_id}, "invoice_number")

    events: list[dict] = []
    for m in moves:
        events.append({
            "kind": "STOCK",
            "type": m.movement_type,               # RECEIVE | SALE | TRANSFER_* | ADJUST
            "at": m.occurred_at.isoformat() if m.occurred_at else None,
            "quantity": int(m.quantity),           # signed: +in / -out
            "unit_cost": float(m.unit_cost) if m.unit_cost is not None else None,
            "warehouse": wh.get(m.warehouse_id),
            "customer": custs.get(m.customer_id),
            "invoice": invs.get(m.invoice_id),
            "user": users.get(m.user_id),
            "note": m.note,
        })
    for p in prices:
        events.append({
            "kind": "PRICE",
            "type": "PRICE_CHANGE",
            "at": p.effective_date.isoformat() if p.effective_date else None,
            "selling_price": float(p.selling_price) if p.selling_price is not None else None,
            "purchase_cost": float(p.purchase_cost) if p.purchase_cost is not None else None,
        })

    events.sort(key=lambda e: e["at"] or "", reverse=True)
    return {
        "product_id": product_id,
        "counts": {"stock_events": len(moves), "price_changes": len(prices)},
        "events": events,
        "provenance": "REAL",
    }
