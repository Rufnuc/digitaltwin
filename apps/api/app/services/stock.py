"""Stock engine — lot receipts, FIFO sale allocation, transfers, adjustments and
traceability. Every physical movement is written to the StockMovement ledger so a
lot (the product's marker) can always answer: when it came in, where it came from,
where it is now, and who bought each unit.

Quantities are whole units. Sale allocation and transfers draw from the oldest
lots first (FIFO). Nothing here invents data — costs come from the lots, buyers
from the invoices.
"""
from __future__ import annotations

import secrets
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.warehouse import MovementType, StockLot, StockMovement, Warehouse


class StockError(ValueError):
    """Raised for invalid stock operations (unknown ids, insufficient stock)."""


def _require(db: Session, model, id_: int, label: str):
    obj = db.get(model, id_)
    if obj is None:
        raise StockError(f"unknown {label} id {id_}")
    return obj


def generate_lot_code(db: Session, product: Product, received: date) -> str:
    """A short, unique, human-scannable lot code, e.g. LOT-BRK12-20260914-9F3A."""
    base = f"LOT-{(product.code or product.id)}-{received:%Y%m%d}"
    for _ in range(20):
        code = f"{base}-{secrets.token_hex(2).upper()}"
        if not db.scalar(select(StockLot.id).where(StockLot.lot_code == code)):
            return code
    raise StockError("could not generate a unique lot code")  # pragma: no cover


def _record(db: Session, lot: StockLot, mtype: str, qty: int, **links) -> StockMovement:
    mv = StockMovement(
        lot_id=lot.id, product_id=lot.product_id, warehouse_id=lot.warehouse_id,
        movement_type=mtype, quantity=qty, unit_cost=lot.unit_cost, **links,
    )
    db.add(mv)
    return mv


def receive_stock(
    db: Session, *, product_id: int, warehouse_id: int, quantity: int,
    unit_cost: float | None = None, received_date: date | None = None,
    supplier_id: int | None = None, purchase_id: int | None = None,
    shipment_ref: str | None = None, vessel_mmsi: int | None = None,
    note: str | None = None, user_id: int | None = None, commit: bool = True,
) -> StockLot:
    """Bring a batch of a product into a warehouse — creates a lot (marker) and a
    RECEIPT movement."""
    if quantity <= 0:
        raise StockError("received quantity must be positive")
    product = _require(db, Product, product_id, "product")
    _require(db, Warehouse, warehouse_id, "warehouse")
    received = received_date or date.today()
    lot = StockLot(
        lot_code=generate_lot_code(db, product, received),
        product_id=product_id, warehouse_id=warehouse_id,
        supplier_id=supplier_id, purchase_id=purchase_id, received_date=received,
        quantity_received=quantity, quantity_remaining=quantity,
        unit_cost=unit_cost if unit_cost is not None else product.purchase_cost,
        shipment_ref=shipment_ref, vessel_mmsi=vessel_mmsi,
        status="IN_STOCK", note=note,
    )
    db.add(lot)
    db.flush()  # assign lot.id
    _record(db, lot, MovementType.RECEIPT, quantity, user_id=user_id, note=note)
    if commit:
        db.commit()
        db.refresh(lot)
    return lot


def receive_batch(
    db: Session, *, warehouse_id: int, lines: list[dict], supplier_id: int | None = None,
    received_date: date | None = None, shipment_ref: str | None = None,
    vessel_mmsi: int | None = None, user_id: int | None = None,
) -> list[StockLot]:
    """Receive several products in one delivery (one supplier / shipment) — a lot per
    line, all committed together."""
    if not lines:
        raise StockError("provide at least one line to receive")
    _require(db, Warehouse, warehouse_id, "warehouse")
    lots = []
    for i, ln in enumerate(lines):
        try:
            lot = receive_stock(
                db, product_id=int(ln["product_id"]), warehouse_id=warehouse_id,
                quantity=int(ln["quantity"]),
                unit_cost=ln.get("unit_cost"),
                supplier_id=supplier_id, received_date=received_date,
                shipment_ref=shipment_ref, vessel_mmsi=vessel_mmsi,
                note=ln.get("note"), user_id=user_id, commit=False,
            )
        except (KeyError, TypeError, ValueError) as e:
            db.rollback()
            raise StockError(f"line {i + 1}: {e}") from e
        lots.append(lot)
    db.commit()
    for lot in lots:
        db.refresh(lot)
    return lots


def _open_lots(db: Session, product_id: int, warehouse_id: int,
               lock: bool = False) -> list[StockLot]:
    """IN_STOCK lots for a product in a warehouse, oldest first (FIFO).

    When ``lock`` is set (any stock-consuming write), the candidate rows are locked
    ``FOR UPDATE`` so two concurrent sales/transfers cannot both draw the same units
    and oversell. (On SQLite, which has no row locks, writes are already serialized.)
    """
    stmt = (
        select(StockLot)
        .where(StockLot.product_id == product_id, StockLot.warehouse_id == warehouse_id,
               StockLot.quantity_remaining > 0)
        .order_by(StockLot.received_date.asc(), StockLot.id.asc())
    )
    if lock:
        stmt = stmt.with_for_update()
    return list(db.scalars(stmt).all())


def on_hand(db: Session, product_id: int, warehouse_id: int) -> int:
    return int(db.scalar(
        select(func.coalesce(func.sum(StockLot.quantity_remaining), 0))
        .where(StockLot.product_id == product_id, StockLot.warehouse_id == warehouse_id)
    ) or 0)


def _draw_fifo(db: Session, product_id: int, warehouse_id: int, quantity: int,
               mtype: str, **links) -> list[dict]:
    """Consume `quantity` from the oldest lots, recording a movement per lot.

    Locks the candidate lots so the availability check and the decrement are atomic
    against other concurrent draws (no oversell)."""
    lots = _open_lots(db, product_id, warehouse_id, lock=True)
    available = sum(lot.quantity_remaining for lot in lots)
    if quantity > available:
        raise StockError(
            f"insufficient stock: need {quantity}, have {available} in warehouse {warehouse_id}")
    allocations: list[dict] = []
    left = quantity
    for lot in lots:
        if left <= 0:
            break
        take = min(left, lot.quantity_remaining)
        lot.quantity_remaining -= take
        if lot.quantity_remaining == 0:
            lot.status = "DEPLETED"
        _record(db, lot, mtype, -take, **links)
        allocations.append({"lot_id": lot.id, "lot_code": lot.lot_code, "quantity": take,
                            "unit_cost": lot.unit_cost})
        left -= take
    return allocations


def allocate_for_sale(
    db: Session, *, product_id: int, warehouse_id: int, quantity: int,
    invoice_id: int | None = None, customer_id: int | None = None,
    user_id: int | None = None, commit: bool = True,
) -> list[dict]:
    """Draw a sale from stock (FIFO), tagging each movement with the buyer/invoice."""
    if quantity <= 0:
        raise StockError("sale quantity must be positive")
    if customer_id is not None:
        _require(db, Customer, customer_id, "customer")
    allocations = _draw_fifo(
        db, product_id, warehouse_id, quantity, MovementType.SALE,
        invoice_id=invoice_id, customer_id=customer_id, user_id=user_id,
    )
    if commit:
        db.commit()
    return allocations


def transfer_stock(
    db: Session, *, product_id: int, from_warehouse_id: int, to_warehouse_id: int,
    quantity: int, user_id: int | None = None, note: str | None = None, commit: bool = True,
) -> dict:
    """Move stock between warehouses, preserving each source lot's lineage (received
    date, supplier, cost) in the destination so traceability is not lost."""
    if from_warehouse_id == to_warehouse_id:
        raise StockError("source and destination warehouses must differ")
    if quantity <= 0:
        raise StockError("transfer quantity must be positive")
    _require(db, Warehouse, to_warehouse_id, "warehouse")
    src_lots = _open_lots(db, product_id, from_warehouse_id, lock=True)
    available = sum(lot.quantity_remaining for lot in src_lots)
    if quantity > available:
        raise StockError(
            f"insufficient stock: need {quantity}, have {available} to transfer")
    moved: list[dict] = []
    left = quantity
    for lot in src_lots:
        if left <= 0:
            break
        take = min(left, lot.quantity_remaining)
        lot.quantity_remaining -= take
        if lot.quantity_remaining == 0:
            lot.status = "DEPLETED"
        _record(db, lot, MovementType.TRANSFER_OUT, -take, user_id=user_id, note=note,
                counterparty_warehouse_id=to_warehouse_id)
        # Recreate the batch in the destination, keeping its lineage.
        dest = StockLot(
            lot_code=f"{lot.lot_code}-T{secrets.token_hex(1).upper()}",
            product_id=product_id, warehouse_id=to_warehouse_id,
            supplier_id=lot.supplier_id, purchase_id=lot.purchase_id,
            received_date=lot.received_date, quantity_received=take, quantity_remaining=take,
            unit_cost=lot.unit_cost, status="IN_STOCK",
            note=f"Transferred from {lot.lot_code}",
        )
        db.add(dest)
        db.flush()
        _record(db, dest, MovementType.TRANSFER_IN, take, user_id=user_id, note=note,
                counterparty_warehouse_id=from_warehouse_id)
        moved.append({"from_lot": lot.lot_code, "to_lot": dest.lot_code, "quantity": take})
        left -= take
    if commit:
        db.commit()
    return {"product_id": product_id, "from_warehouse_id": from_warehouse_id,
            "to_warehouse_id": to_warehouse_id, "quantity": quantity, "lots": moved}


def adjust_lot(
    db: Session, *, lot_id: int, delta: int, reason: str, user_id: int | None = None,
    commit: bool = True,
) -> StockLot:
    """Correct a lot's remaining quantity (stock count, damage, loss)."""
    lot = _require(db, StockLot, lot_id, "lot")
    if delta == 0:
        raise StockError("adjustment delta cannot be zero")
    if lot.quantity_remaining + delta < 0:
        raise StockError("adjustment would make remaining quantity negative")
    lot.quantity_remaining += delta
    lot.status = "DEPLETED" if lot.quantity_remaining == 0 else "IN_STOCK"
    _record(db, lot, MovementType.ADJUSTMENT, delta, user_id=user_id, note=reason)
    if commit:
        db.commit()
        db.refresh(lot)
    return lot


# --------------------------------------------------------------------------- #
# Reads — the marker (lot) traceability views.
# --------------------------------------------------------------------------- #
def _name_maps(db: Session) -> dict:
    return {
        "warehouse": dict(db.execute(select(Warehouse.id, Warehouse.name)).all()),
        "product": dict(db.execute(select(Product.id, Product.name)).all()),
        "product_image": dict(db.execute(select(Product.id, Product.image_url)).all()),
        "customer": dict(db.execute(select(Customer.id, Customer.name)).all()),
        "supplier": dict(db.execute(select(Supplier.id, Supplier.name)).all()),
    }


def _movement_dict(m: StockMovement, names: dict) -> dict:
    return {
        "id": m.id,
        "type": m.movement_type,
        "quantity": m.quantity,
        "occurred_at": m.occurred_at.isoformat() if m.occurred_at else None,
        "warehouse": names["warehouse"].get(m.warehouse_id),
        "invoice_id": m.invoice_id,
        "customer": names["customer"].get(m.customer_id) if m.customer_id else None,
        "counterparty_warehouse": (
            names["warehouse"].get(m.counterparty_warehouse_id)
            if m.counterparty_warehouse_id else None),
        "unit_cost": m.unit_cost,
        "note": m.note,
    }


def _lot_dict(lot: StockLot, names: dict, movements: list | None = None) -> dict:
    d = {
        "id": lot.id,
        "lot_code": lot.lot_code,
        "product_id": lot.product_id,
        "product": names["product"].get(lot.product_id),
        "product_image": names["product_image"].get(lot.product_id),
        "warehouse_id": lot.warehouse_id,
        "warehouse": names["warehouse"].get(lot.warehouse_id),
        "supplier": names["supplier"].get(lot.supplier_id) if lot.supplier_id else None,
        "purchase_id": lot.purchase_id,
        "received_date": lot.received_date.isoformat() if lot.received_date else None,
        "quantity_received": lot.quantity_received,
        "quantity_remaining": lot.quantity_remaining,
        "unit_cost": lot.unit_cost,
        "shipment_ref": lot.shipment_ref,
        "vessel_mmsi": lot.vessel_mmsi,
        "status": lot.status,
        "note": lot.note,
    }
    if movements is not None:
        d["movements"] = movements
    return d


def _vessel_snapshot(mmsi: int | None) -> dict | None:
    """If the lot names a vessel we track, its latest known status (REAL AIS)."""
    if not mmsi:
        return None
    from app.services.shipping import collector

    v = collector.store.vessels.get(int(mmsi))
    if not v:
        return {"mmsi": mmsi, "tracked": False}
    return {
        "mmsi": mmsi, "tracked": True, "name": v.get("name"),
        "region": v.get("region"), "origin_region": v.get("origin_region"),
        "bound_for_nigeria": v.get("bound_for_nigeria"),
        "arrived_nigeria": v.get("arrived_nigeria"),
        "last_seen": v.get("last_seen"),
    }


def list_lots(db: Session, *, product_id: int | None = None, warehouse_id: int | None = None,
              in_stock_only: bool = False, limit: int = 200, offset: int = 0) -> dict:
    stmt = select(StockLot)
    if product_id:
        stmt = stmt.where(StockLot.product_id == product_id)
    if warehouse_id:
        stmt = stmt.where(StockLot.warehouse_id == warehouse_id)
    if in_stock_only:
        stmt = stmt.where(StockLot.quantity_remaining > 0)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(db.scalars(
        stmt.order_by(StockLot.received_date.desc(), StockLot.id.desc()).limit(limit).offset(offset)
    ).all())
    names = _name_maps(db)
    return {"items": [_lot_dict(lot, names) for lot in rows], "total": total,
            "provenance": "REAL"}


def lot_detail(db: Session, lot_id: int) -> dict | None:
    """A single marker with its full movement history — who bought it, when it came
    in, where it moved."""
    lot = db.get(StockLot, lot_id)
    if lot is None:
        return None
    names = _name_maps(db)
    moves = list(db.scalars(
        select(StockMovement).where(StockMovement.lot_id == lot_id)
        .order_by(StockMovement.occurred_at.asc(), StockMovement.id.asc())
    ).all())
    buyers = sorted({names["customer"].get(m.customer_id) for m in moves
                     if m.movement_type == MovementType.SALE and m.customer_id}
                    - {None})
    # A running balance after each movement — the lot's state at every "version".
    move_dicts = []
    balance = 0
    for m in moves:
        balance += m.quantity
        move_dicts.append({**_movement_dict(m, names), "version": len(move_dicts) + 1,
                           "balance_after": balance})
    return {
        **_lot_dict(lot, names, move_dicts),
        "sold_to": buyers,
        "invoices": sorted({m.invoice_id for m in moves if m.invoice_id}),
        "vessel": _vessel_snapshot(lot.vessel_mmsi),
    }


def on_hand_totals(db: Session) -> dict[int, int]:
    """Authoritative on-hand per product: lot ledger when the product has lots, else
    the legacy Inventory scalar (products predating the lot ledger). One source of
    truth — the lot ledger wins wherever it exists."""
    from app.models.inventory import Inventory

    lot_rows = db.execute(
        select(StockLot.product_id, func.sum(StockLot.quantity_remaining))
        .where(StockLot.quantity_remaining > 0)
        .group_by(StockLot.product_id)
    ).all()
    totals = {pid: int(qty or 0) for pid, qty in lot_rows}
    lot_products = set(totals)
    legacy = db.execute(
        select(Inventory.product_id, func.sum(Inventory.quantity_on_hand))
        .group_by(Inventory.product_id)
    ).all()
    for pid, qty in legacy:
        if pid not in lot_products:  # only where the ledger has nothing to say
            totals[pid] = int(qty or 0)
    return totals


def stock_value(db: Session) -> float:
    """Total inventory value (units × unit cost), lot-authoritative: value from lots
    where they exist, legacy Inventory only for products with no lots."""
    from app.models.inventory import Inventory

    lot_val = float(db.scalar(
        select(func.coalesce(func.sum(StockLot.quantity_remaining * StockLot.unit_cost), 0))
        .where(StockLot.quantity_remaining > 0)
    ) or 0.0)
    lot_products = select(StockLot.product_id).where(StockLot.quantity_remaining > 0).distinct()
    legacy_val = float(db.scalar(
        select(func.coalesce(func.sum(Inventory.quantity_on_hand * Inventory.unit_cost), 0))
        .where(Inventory.product_id.notin_(lot_products))
    ) or 0.0)
    return round(lot_val + legacy_val, 2)


def levels(db: Session, *, q: str | None = None, warehouse_id: int | None = None,
           category: str | None = None, low_stock: bool = False,
           sort: str = "on_hand", sort_dir: str = "desc",
           limit: int = 200, offset: int = 0) -> dict:
    """Per-product stock levels from the lot ledger — current on-hand and value,
    with search (name/code), warehouse and category filters, a low-stock filter
    (on-hand at or below the product's reorder level), and sorting."""
    agg = select(
        StockLot.product_id.label("pid"),
        func.coalesce(func.sum(StockLot.quantity_remaining), 0).label("on_hand"),
        func.coalesce(func.sum(StockLot.quantity_remaining * StockLot.unit_cost), 0).label("value"),
    ).where(StockLot.quantity_remaining > 0)
    if warehouse_id is not None:
        agg = agg.where(StockLot.warehouse_id == warehouse_id)
    agg = agg.group_by(StockLot.product_id).subquery()

    on_hand = func.coalesce(agg.c.on_hand, 0)
    value = func.coalesce(agg.c.value, 0.0)
    stmt = select(Product, on_hand.label("on_hand"), value.label("value")).outerjoin(
        agg, agg.c.pid == Product.id
    ).where(Product.deleted_at.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.code.ilike(like)))
    if category:
        stmt = stmt.where(Product.category == category)
    if warehouse_id is not None:
        stmt = stmt.where(agg.c.pid.is_not(None))  # only products held in that warehouse
    if low_stock:
        stmt = stmt.where(Product.reorder_level.is_not(None), on_hand <= Product.reorder_level)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))

    sort_map = {"on_hand": on_hand, "value": value, "name": Product.name,
                "code": Product.code, "reorder_level": Product.reorder_level}
    col = sort_map.get(sort, on_hand)
    stmt = stmt.order_by(col.desc() if sort_dir == "desc" else col.asc())

    rows = db.execute(stmt.limit(limit).offset(offset)).all()
    items = []
    for prod, oh, val in rows:
        oh = int(oh or 0)
        rl = prod.reorder_level
        items.append({
            "product_id": prod.id, "code": prod.code, "name": prod.name,
            "category": prod.category, "on_hand": oh,
            "value": round(float(val or 0), 2),
            "reorder_level": rl, "low": rl is not None and oh <= rl,
        })

    cats = [c for (c,) in db.execute(
        select(Product.category).where(Product.category.is_not(None),
                                       Product.deleted_at.is_(None))
        .distinct().order_by(Product.category)
    ).all()]
    return {"items": items, "total": int(total or 0), "limit": limit, "offset": offset,
            "sort": sort, "sort_dir": sort_dir, "categories": cats}


def warehouse_summary(db: Session, warehouse_id: int) -> dict | None:
    """A warehouse at a glance: value of goods stored, quantity available, the
    products held there, and the most recent stock movements in and out."""
    wh = db.get(Warehouse, warehouse_id)
    if wh is None or getattr(wh, "deleted_at", None) is not None:
        return None

    rows = db.execute(
        select(StockLot.product_id, Product.code, Product.name,
               func.coalesce(func.sum(StockLot.quantity_remaining), 0),
               func.coalesce(func.sum(StockLot.quantity_remaining * StockLot.unit_cost), 0))
        .join(Product, Product.id == StockLot.product_id, isouter=True)
        .where(StockLot.warehouse_id == warehouse_id, StockLot.quantity_remaining > 0)
        .group_by(StockLot.product_id, Product.code, Product.name)
        .order_by(func.sum(StockLot.quantity_remaining * StockLot.unit_cost).desc())
    ).all()
    products = [{"product_id": pid, "code": code, "name": name,
                "on_hand": int(q or 0), "value": round(float(v or 0), 2)}
               for pid, code, name, q, v in rows]
    total_units = sum(p["on_hand"] for p in products)
    total_value = round(sum(p["value"] for p in products), 2)
    open_lots = db.scalar(
        select(func.count()).select_from(StockLot)
        .where(StockLot.warehouse_id == warehouse_id, StockLot.quantity_remaining > 0)
    ) or 0

    mv = db.execute(
        select(StockMovement, Product.name)
        .join(Product, Product.id == StockMovement.product_id, isouter=True)
        .where(StockMovement.warehouse_id == warehouse_id)
        .order_by(StockMovement.id.desc()).limit(20)
    ).all()
    movements = [{"type": m.movement_type, "product": pname,
                  "quantity": int(m.quantity or 0), "note": m.note,
                  "occurred_at": m.occurred_at.isoformat() if m.occurred_at else None}
                 for m, pname in mv]

    return {"warehouse_id": wh.id, "code": wh.code, "name": wh.name,
            "location": wh.location, "type": wh.type, "status": wh.status,
            "total_value": total_value, "total_units": int(total_units),
            "product_count": len(products), "open_lot_count": int(open_lots),
            "products": products, "recent_movements": movements, "provenance": "REAL"}


def on_hand_by_warehouse(db: Session, product_id: int) -> list[dict]:
    """Where a product's stock sits right now, across all warehouses."""
    rows = db.execute(
        select(StockLot.warehouse_id, func.sum(StockLot.quantity_remaining))
        .where(StockLot.product_id == product_id, StockLot.quantity_remaining > 0)
        .group_by(StockLot.warehouse_id)
    ).all()
    names = _name_maps(db)
    return [{"warehouse_id": wid, "warehouse": names["warehouse"].get(wid), "on_hand": int(qty)}
            for wid, qty in rows]
