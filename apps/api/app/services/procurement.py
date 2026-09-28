"""Procurement — raise a request to a supplier, order it, and receive it into stock.

A purchase moves through REQUEST → ORDERED → RECEIVED. Receiving draws the goods
into the lot ledger (linking supplier ↔ product ↔ warehouse) and rolls the transport
cost into each unit's landed cost, so freight flows through to COGS.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.models.purchase import Purchase, PurchaseDocument, PurchaseLine
from app.models.supplier import Supplier
from app.services import stock
from app.services.storage import get_storage

STATUSES = ("REQUEST", "ORDERED", "RECEIVED", "CANCELLED")


def _next_reference(db: Session) -> str:
    year = date.today().year
    prefix = f"PR-{year}-"
    n = 0
    for (ref,) in db.execute(
        select(Purchase.reference).where(Purchase.reference.like(f"{prefix}%"))
    ).all():
        try:
            n = max(n, int(ref[len(prefix):]))
        except ValueError:
            continue
    return f"{prefix}{n + 1:05d}"


def _product_names(db: Session, ids: set[int]) -> dict[int, tuple[str, str]]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {pid: (code, name) for pid, code, name in db.execute(
        select(Product.id, Product.code, Product.name).where(Product.id.in_(ids))).all()}


def _to_dict(db: Session, p: Purchase, with_lines: bool = False) -> dict:
    sup = db.get(Supplier, p.supplier_id) if p.supplier_id else None
    d = {
        "id": p.id, "reference": p.reference, "status": p.status,
        "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
        "supplier_id": p.supplier_id, "supplier_name": sup.name if sup else None,
        "currency": p.currency, "subtotal": float(p.subtotal or 0),
        "transport_cost": float(p.transport_cost or 0), "total": float(p.total or 0),
        "amount_paid": float(p.amount_paid or 0), "payment_status": p.payment_status,
        "line_count": len(p.lines),
        "document_count": len(p.documents),
    }
    if with_lines:
        names = _product_names(db, {ln.product_id for ln in p.lines})
        d["lines"] = [{
            "product_id": ln.product_id,
            "product_code": names.get(ln.product_id, (None, None))[0],
            "product_name": names.get(ln.product_id, (None, None))[1],
            "description": ln.original_description,
            "quantity": float(ln.quantity or 0), "unit_cost": float(ln.unit_cost or 0),
            "line_total": float(ln.line_total or 0),
        } for ln in p.lines]
    return d


def create_request(db: Session, *, supplier_id: int | None, currency: str = "NGN",
                   lines: list[dict], purchase_date: date | None = None,
                   user_id: int | None = None) -> dict:
    if not lines:
        return {"status": "ERROR", "error": "a request needs at least one item"}
    if supplier_id is not None and db.get(Supplier, supplier_id) is None:
        return {"status": "ERROR", "error": "supplier not found"}
    p = Purchase(
        reference=_next_reference(db), purchase_date=purchase_date or date.today(),
        supplier_id=supplier_id, currency=currency, status="REQUEST",
    )
    subtotal = 0.0
    for ln in lines:
        qty = float(ln.get("quantity") or 0)
        cost = float(ln.get("unit_cost") or 0)
        lt = round(qty * cost, 2)
        subtotal += lt
        p.lines.append(PurchaseLine(
            product_id=ln.get("product_id"),
            original_description=ln.get("description"),
            quantity=qty, unit_cost=cost, line_total=lt,
        ))
    p.subtotal = round(subtotal, 2)
    p.total = round(subtotal, 2)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"status": "OK", **_to_dict(db, p, with_lines=True)}


def set_status(db: Session, purchase_id: int, new_status: str) -> dict:
    p = db.get(Purchase, purchase_id)
    if p is None:
        return {"status": "NOT_FOUND"}
    if new_status not in STATUSES:
        return {"status": "ERROR", "error": f"invalid status '{new_status}'"}
    if new_status == "RECEIVED":
        return {"status": "ERROR", "error": "use the receive action to mark RECEIVED"}
    p.status = new_status
    db.commit()
    db.refresh(p)
    return {"status": "OK", **_to_dict(db, p, with_lines=True)}


def receive(db: Session, *, purchase_id: int, warehouse_id: int, transport_cost: float = 0.0,
            received_date: date | None = None, user_id: int | None = None) -> dict:
    """Receive an ordered purchase into a warehouse: create a lot per product line
    (linking supplier ↔ product ↔ warehouse) with the transport cost spread across
    units as landed cost. Marks the purchase RECEIVED."""
    p = db.scalars(
        select(Purchase).options(selectinload(Purchase.lines), selectinload(Purchase.documents)).where(Purchase.id == purchase_id)
    ).first()
    if p is None:
        return {"status": "NOT_FOUND"}
    if p.status == "RECEIVED":
        return {"status": "ERROR", "error": "this purchase has already been received"}
    if p.status == "CANCELLED":
        return {"status": "ERROR", "error": "cannot receive a cancelled purchase"}
    stock_lines = [ln for ln in p.lines if ln.product_id and (ln.quantity or 0) > 0]
    if not stock_lines:
        return {"status": "ERROR", "error": "no stock lines to receive"}

    transport_cost = round(float(transport_cost or 0), 2)
    total_units = sum(int(ln.quantity) for ln in stock_lines)
    freight_per_unit = (transport_cost / total_units) if total_units else 0.0

    try:
        for ln in stock_lines:
            landed = round(float(ln.unit_cost or 0) + freight_per_unit, 2)
            stock.receive_stock(
                db, product_id=ln.product_id, warehouse_id=warehouse_id,
                quantity=int(ln.quantity), unit_cost=landed, supplier_id=p.supplier_id,
                purchase_id=p.id, received_date=received_date, user_id=user_id, commit=False,
            )
    except stock.StockError as e:
        db.rollback()
        return {"status": "ERROR", "error": str(e)}

    p.transport_cost = transport_cost
    p.total = round(float(p.subtotal or 0) + transport_cost, 2)
    p.status = "RECEIVED"
    db.commit()
    db.refresh(p)
    return {"status": "OK", **_to_dict(db, p, with_lines=True)}


def get_purchase(db: Session, purchase_id: int) -> dict | None:
    p = db.scalars(
        select(Purchase).options(selectinload(Purchase.lines), selectinload(Purchase.documents)).where(Purchase.id == purchase_id)
    ).first()
    if p is None:
        return None
    return _to_dict(db, p, with_lines=True)


def list_purchases(db: Session, *, status: str | None = None, supplier_id: int | None = None,
                   q: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    stmt = select(Purchase).options(selectinload(Purchase.lines), selectinload(Purchase.documents))
    if status:
        stmt = stmt.where(Purchase.status == status)
    if supplier_id is not None:
        stmt = stmt.where(Purchase.supplier_id == supplier_id)
    if q:
        stmt = stmt.where(Purchase.reference.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Purchase.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [_to_dict(db, p) for p in rows], "total": int(total or 0),
            "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# Shipping documents attached to a purchase (waybills, packing lists, B/L,
# supplier invoices, proof of payment, photos). The file bytes live in object
# storage; a PurchaseDocument row indexes it against the purchase.
# ---------------------------------------------------------------------------

def _doc_dict(d: PurchaseDocument) -> dict:
    return {
        "id": d.id, "purchase_id": d.purchase_id, "payment_id": d.payment_id,
        "filename": d.filename,
        "content_type": d.content_type, "size_bytes": d.size_bytes,
        "kind": d.kind, "note": d.note,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def add_document(db: Session, *, purchase_id: int, filename: str, data: bytes,
                 content_type: str | None = None, kind: str = "shipping",
                 note: str | None = None, payment_id: int | None = None,
                 user_id: int | None = None) -> dict | None:
    """Store an uploaded document and attach it to the purchase — or, when
    payment_id is given, to a specific payment as a receipt/proof.
    Returns None when the purchase does not exist."""
    p = db.get(Purchase, purchase_id)
    if p is None:
        return None
    key = get_storage().save(data, filename or "document", content_type)
    doc = PurchaseDocument(
        purchase_id=purchase_id, payment_id=payment_id, filename=filename or "document",
        content_type=content_type, storage_key=key, size_bytes=len(data),
        kind=(kind or "shipping")[:32], note=note, uploaded_by_user_id=user_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _doc_dict(doc)


def list_documents(db: Session, purchase_id: int,
                   payment_id: int | None = None, payment_only: bool = False) -> list[dict]:
    """Documents for a purchase. By default returns only purchase-level (shipping)
    documents — those not tied to a payment. Pass payment_id to get one payment's
    receipts, or payment_only=True for every payment receipt on the purchase."""
    stmt = select(PurchaseDocument).where(PurchaseDocument.purchase_id == purchase_id)
    if payment_id is not None:
        stmt = stmt.where(PurchaseDocument.payment_id == payment_id)
    elif payment_only:
        stmt = stmt.where(PurchaseDocument.payment_id.is_not(None))
    else:
        stmt = stmt.where(PurchaseDocument.payment_id.is_(None))
    rows = db.scalars(stmt.order_by(PurchaseDocument.id)).all()
    return [_doc_dict(d) for d in rows]


def get_document(db: Session, purchase_id: int, doc_id: int) -> PurchaseDocument | None:
    d = db.get(PurchaseDocument, doc_id)
    if d is None or d.purchase_id != purchase_id:
        return None
    return d


def delete_document(db: Session, purchase_id: int, doc_id: int) -> bool:
    d = get_document(db, purchase_id, doc_id)
    if d is None:
        return False
    db.delete(d)
    db.commit()
    return True
