"""Per-product analytics: units bought vs sold over time, current stock and the
revenue it has earned — all from the lot ledger and invoices (never invented)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.invoice import InvoiceLine
from app.models.product import Product
from app.models.warehouse import MovementType, StockLot, StockMovement


def _months_back(n: int) -> list[str]:
    today = date.today()
    y, m = today.year, today.month
    keys: list[str] = []
    for _ in range(n):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(keys))


def product_analytics(db: Session, product_id: int, months: int = 12) -> dict | None:
    prod = db.get(Product, product_id)
    if prod is None or getattr(prod, "deleted_at", None) is not None:
        return None

    keys = _months_back(months)
    received = {k: 0 for k in keys}
    sold = {k: 0 for k in keys}

    movements = db.execute(
        select(StockMovement.movement_type, StockMovement.quantity, StockMovement.occurred_at)
        .where(StockMovement.product_id == product_id)
    ).all()
    for mtype, qty, occurred in movements:
        if not occurred:
            continue
        k = occurred.strftime("%Y-%m")
        if k not in received:
            continue
        if mtype == MovementType.RECEIPT:
            received[k] += int(qty or 0)
        elif mtype == MovementType.SALE:
            sold[k] += abs(int(qty or 0))
    monthly = [{"month": k, "received": received[k], "sold": sold[k]} for k in keys]

    total_received = int(db.scalar(
        select(func.coalesce(func.sum(StockMovement.quantity), 0))
        .where(StockMovement.product_id == product_id,
               StockMovement.movement_type == MovementType.RECEIPT)) or 0)
    total_sold = abs(int(db.scalar(
        select(func.coalesce(func.sum(StockMovement.quantity), 0))
        .where(StockMovement.product_id == product_id,
               StockMovement.movement_type == MovementType.SALE)) or 0))
    on_hand = int(db.scalar(
        select(func.coalesce(func.sum(StockLot.quantity_remaining), 0))
        .where(StockLot.product_id == product_id)) or 0)
    stock_value = round(float(db.scalar(
        select(func.coalesce(func.sum(StockLot.quantity_remaining * StockLot.unit_cost), 0))
        .where(StockLot.product_id == product_id, StockLot.quantity_remaining > 0)) or 0.0), 2)
    revenue = round(float(db.scalar(
        select(func.coalesce(func.sum(InvoiceLine.line_total), 0))
        .where(InvoiceLine.product_id == product_id)) or 0.0), 2)

    return {
        "product_id": prod.id, "product_code": prod.code, "product_name": prod.name,
        "total_received": total_received, "total_sold": total_sold,
        "on_hand": on_hand, "stock_value": stock_value, "revenue": revenue,
        "reorder_level": prod.reorder_level,
        "monthly": monthly, "provenance": "REAL",
    }
