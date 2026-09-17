"""One-time reconciliation for the legacy-Inventory cutover.

The lot ledger is authoritative for on-hand; the legacy ``Inventory.quantity_on_hand``
scalar survives only as a fallback for products that predate the ledger. Where a
product has lots but its legacy scalar disagrees, the scalar is stale. This module
finds those divergences (dry-run) and, only on an explicit operator step, aligns the
legacy scalar to the lot-derived truth (audited, conservative — it never touches a
product that has no lots).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.product import Product
from app.models.warehouse import StockLot


def divergences(db: Session) -> list[dict]:
    """Products whose lot-derived on-hand differs from the legacy Inventory scalar.

    Only products that actually have lots are considered (the ledger is authoritative
    there); legacy-only products are left alone."""
    lot = {
        pid: int(qty or 0)
        for pid, qty in db.execute(
            select(StockLot.product_id, func.sum(StockLot.quantity_remaining))
            .where(StockLot.quantity_remaining > 0)
            .group_by(StockLot.product_id)
        ).all()
    }
    legacy = {
        pid: int(qty or 0)
        for pid, qty in db.execute(
            select(Inventory.product_id, func.sum(Inventory.quantity_on_hand))
            .group_by(Inventory.product_id)
        ).all()
    }
    names = {
        pid: (code, name)
        for pid, code, name in db.execute(
            select(Product.id, Product.code, Product.name)
            .where(Product.id.in_(lot.keys()))
        ).all()
    } if lot else {}

    out: list[dict] = []
    for pid, lot_qty in lot.items():
        leg = legacy.get(pid, 0)
        if lot_qty != leg:
            code, name = names.get(pid, (None, None))
            out.append({
                "product_id": pid, "code": code, "name": name,
                "lot_on_hand": lot_qty, "legacy_on_hand": leg, "delta": lot_qty - leg,
            })
    out.sort(key=lambda d: abs(d["delta"]), reverse=True)
    return out


def reconcile(db: Session, *, apply: bool = False, user_id: int | None = None) -> dict:
    """Report divergences (default) or align the legacy scalar to the lot ledger.

    Dry-run by default: ``apply`` must be set explicitly to write. Writes are
    conservative (only products that have lots) and audited.
    """
    divs = divergences(db)
    if not apply:
        return {"mode": "dry_run", "divergent_products": len(divs), "items": divs}

    for d in divs:
        inv = db.scalar(select(Inventory).where(Inventory.product_id == d["product_id"]))
        if inv is None:
            inv = Inventory(product_id=d["product_id"], quantity_on_hand=0)
            db.add(inv)
        inv.quantity_on_hand = d["lot_on_hand"]
    db.commit()

    if divs:
        from app.core.enums import AuditAction
        from app.services import audit
        audit.record(
            db, action=AuditAction.UPDATE, user_id=user_id, entity_type="inventory",
            new_value={"reconciled_products": [d["product_id"] for d in divs]},
            source="inventory_reconcile",
            summary=f"aligned legacy Inventory to lot ledger for {len(divs)} product(s)",
        )
    return {"mode": "applied", "divergent_products": len(divs), "items": divs}
