"""Supplier traceability — tie products ↔ suppliers ↔ warehouses, with each
supplier's shipments and payments.

The chain already exists on StockLot (product, supplier, warehouse, purchase,
shipment_ref, vessel, received_date, landed unit cost); this reads it back as a
supplier's full picture, and a product's sources.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.purchase import Purchase, SupplierPayment
from app.models.supplier import Supplier
from app.models.warehouse import MovementType, StockLot, StockMovement, Warehouse


def product_suppliers(db: Session, product_id: int) -> list[dict]:
    """Which suppliers have supplied this product (from received stock lots)."""
    rows = db.execute(
        select(
            StockLot.supplier_id, Supplier.name,
            func.count(StockLot.id), func.coalesce(func.sum(StockLot.quantity_received), 0),
            func.max(StockLot.received_date),
        )
        .join(Supplier, Supplier.id == StockLot.supplier_id, isouter=True)
        .where(StockLot.product_id == product_id)
        .group_by(StockLot.supplier_id, Supplier.name)
        .order_by(func.sum(StockLot.quantity_received).desc())
    ).all()
    return [
        {"supplier_id": sid, "supplier_name": name or "Unknown",
         "lots": int(lots), "total_received": int(qty or 0),
         "last_received": lr.isoformat() if lr else None}
        for sid, name, lots, qty, lr in rows
    ]


def supplier_detail(db: Session, supplier_id: int) -> dict:
    """A supplier's full traceability: products supplied, warehouses, shipments,
    what we owe them, and the payments we've made (with bank detail)."""
    sup = db.get(Supplier, supplier_id)
    if sup is None:
        return {"status": "NOT_FOUND"}

    # Products supplied.
    prod_rows = db.execute(
        select(
            StockLot.product_id, Product.code, Product.name,
            func.coalesce(func.sum(StockLot.quantity_received), 0),
            func.max(StockLot.received_date),
        )
        .join(Product, Product.id == StockLot.product_id, isouter=True)
        .where(StockLot.supplier_id == supplier_id)
        .group_by(StockLot.product_id, Product.code, Product.name)
        .order_by(func.sum(StockLot.quantity_received).desc())
    ).all()
    products = [
        {"product_id": pid, "product_code": code, "product_name": name,
         "total_received": int(qty or 0), "last_received": lr.isoformat() if lr else None}
        for pid, code, name, qty, lr in prod_rows
    ]

    # Shipments (lots), newest first, with warehouse + vessel/shipping ref.
    ship_rows = db.execute(
        select(StockLot, Product.name, Warehouse.name)
        .join(Product, Product.id == StockLot.product_id, isouter=True)
        .join(Warehouse, Warehouse.id == StockLot.warehouse_id, isouter=True)
        .where(StockLot.supplier_id == supplier_id)
        .order_by(StockLot.received_date.desc(), StockLot.id.desc())
        .limit(100)
    ).all()
    shipments = [
        {"lot_code": lot.lot_code, "product": pname, "warehouse": wname,
         "received_date": lot.received_date.isoformat() if lot.received_date else None,
         "quantity": int(lot.quantity_received or 0),
         "unit_cost": float(lot.unit_cost) if lot.unit_cost is not None else None,
         "shipment_ref": lot.shipment_ref, "vessel_mmsi": lot.vessel_mmsi,
         "purchase_id": lot.purchase_id}
        for lot, pname, wname in ship_rows
    ]

    warehouses = sorted({s["warehouse"] for s in shipments if s["warehouse"]})

    # Payables: purchases + payments with bank detail.
    from app.services import payables
    purchases = db.scalars(
        select(Purchase).where(Purchase.supplier_id == supplier_id)
        .order_by(Purchase.purchase_date.desc())
    ).all()
    owed = round(sum(payables.balance(p) for p in purchases if p.payment_status != "PAID"), 2)
    total_paid = round(sum(float(p.amount_paid or 0) for p in purchases), 2)
    # Statement: every purchase with what it cost, what's paid, and the balance.
    statement = [
        {"id": p.id, "reference": p.reference,
         "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
         "status": p.status, "total": float(p.total or 0),
         "amount_paid": float(p.amount_paid or 0), "balance": payables.balance(p),
         "payment_status": p.payment_status}
        for p in purchases
    ]
    pay_rows = db.scalars(
        select(SupplierPayment).where(SupplierPayment.supplier_id == supplier_id,
                                      SupplierPayment.status == "CONFIRMED")
        .order_by(SupplierPayment.paid_at.desc())
    ).all()
    payments = [
        {"amount": float(p.amount), "method": p.method, "paid_at": p.paid_at.isoformat(),
         "reference": p.reference, "txid": p.txid, "purchase_id": p.purchase_id,
         "from_account": p.from_account, "from_name": p.from_name,
         "to_account": p.to_account, "to_name": p.to_name}
        for p in pay_rows
    ]

    return {
        "status": "OK",
        "supplier_id": supplier_id, "supplier_code": sup.code, "supplier_name": sup.name,
        "location": sup.location, "currency": sup.currency,
        "lead_time_days": sup.lead_time_days, "reliability_score": sup.reliability_score,
        "products": products,
        "warehouses": warehouses,
        "shipments": shipments,
        "we_owe": owed,
        "total_paid": total_paid,
        "statement": statement,
        "payments": payments,
        "slow_movers": _slow_movers(db, [p["product_id"] for p in products if p["product_id"]]),
        "provenance": "REAL",
    }


def _slow_movers(db: Session, product_ids: list[int]) -> list[dict]:
    """For products this supplier supplied: how many we received, sold, and still hold —
    so barely-sold lines (money tied up on the shelf) stand out."""
    if not product_ids:
        return []
    received = dict(db.execute(
        select(StockLot.product_id, func.coalesce(func.sum(StockLot.quantity_received), 0))
        .where(StockLot.product_id.in_(product_ids)).group_by(StockLot.product_id)).all())
    on_hand = dict(db.execute(
        select(StockLot.product_id, func.coalesce(func.sum(StockLot.quantity_remaining), 0))
        .where(StockLot.product_id.in_(product_ids)).group_by(StockLot.product_id)).all())
    # Units sold = SALE movements in the lot ledger (quantities are signed -out).
    sold = dict(db.execute(
        select(StockMovement.product_id, func.coalesce(func.sum(-StockMovement.quantity), 0))
        .where(StockMovement.product_id.in_(product_ids),
               StockMovement.movement_type == MovementType.SALE)
        .group_by(StockMovement.product_id)).all())
    names = {pid: (code, name) for pid, code, name in db.execute(
        select(Product.id, Product.code, Product.name).where(Product.id.in_(product_ids))).all()}
    rows = []
    for pid in product_ids:
        code, name = names.get(pid, (None, None))
        rows.append({"product_id": pid, "product_code": code, "product_name": name,
                     "received": int(received.get(pid, 0) or 0),
                     "sold": int(sold.get(pid, 0) or 0),
                     "on_hand": int(on_hand.get(pid, 0) or 0)})
    # Worst sellers first: least sold, most still on hand.
    rows.sort(key=lambda r: (r["sold"], -r["on_hand"]))
    return rows
