"""Waybill service — raise and track dispatch records against invoices."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.user import User
from app.models.waybill import WAYBILL_STATUSES, Waybill

_EDITABLE = ("apprentice_name", "transport_company", "driver_phone", "vehicle_info",
             "station", "receiver_name", "receiver_phone", "destination", "notes")


def _next_number(db: Session) -> str:
    """Sequential, human-scannable: WB-2026-00001."""
    year = date.today().year
    prefix = f"WB-{year}-"
    n = 0
    for (num,) in db.execute(
        select(Waybill.waybill_number).where(Waybill.waybill_number.like(f"{prefix}%"))
    ).all():
        try:
            n = max(n, int(num[len(prefix):]))
        except ValueError:
            continue
    return f"{prefix}{n + 1:05d}"


def _invoice_meta(db: Session, invoice_ids: set[int]) -> dict[int, dict]:
    if not invoice_ids:
        return {}
    rows = db.execute(
        select(Invoice.id, Invoice.invoice_number, Invoice.total, Invoice.customer_id,
               Customer.name)
        .join(Customer, Customer.id == Invoice.customer_id, isouter=True)
        .where(Invoice.id.in_(invoice_ids))
    ).all()
    return {r[0]: {"invoice_number": r[1], "invoice_total": float(r[2] or 0),
                   "customer_id": r[3], "customer_name": r[4]} for r in rows}


def _user_names(db: Session, ids: set[int]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {uid: (n or e) for uid, n, e in db.execute(
        select(User.id, User.full_name, User.email).where(User.id.in_(ids))).all()}


def _to_dict(wb: Waybill, inv: dict | None = None, creator: str | None = None) -> dict:
    inv = inv or {}
    return {
        "id": wb.id, "waybill_number": wb.waybill_number, "invoice_id": wb.invoice_id,
        "status": wb.status,
        "dispatched_at": wb.dispatched_at.isoformat() if wb.dispatched_at else None,
        "apprentice_name": wb.apprentice_name, "transport_company": wb.transport_company,
        "driver_phone": wb.driver_phone, "vehicle_info": wb.vehicle_info,
        "station": wb.station, "receiver_name": wb.receiver_name,
        "receiver_phone": wb.receiver_phone, "destination": wb.destination,
        "notes": wb.notes,
        "created_at": wb.created_at.isoformat() if wb.created_at else None,
        "created_by": creator,
        "invoice_number": inv.get("invoice_number"),
        "invoice_total": inv.get("invoice_total"),
        "customer_id": inv.get("customer_id"),
        "customer_name": inv.get("customer_name"),
    }


def create_waybill(db: Session, *, invoice_id: int, user_id: int | None = None,
                   status: str = "PENDING", dispatched_at: datetime | None = None,
                   **fields) -> dict:
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        return {"status": "NOT_FOUND", "error": f"invoice {invoice_id} not found"}
    if status not in WAYBILL_STATUSES:
        return {"status": "ERROR", "error": f"invalid status '{status}'"}
    wb = Waybill(
        waybill_number=_next_number(db), invoice_id=invoice_id, status=status,
        created_by_user_id=user_id,
        **{k: fields.get(k) for k in _EDITABLE},
    )
    # If it's being raised already-dispatched, stamp the send time.
    if status in ("DISPATCHED", "DELIVERED"):
        wb.dispatched_at = dispatched_at or datetime.now(timezone.utc)
    db.add(wb)
    db.commit()
    db.refresh(wb)
    meta = _invoice_meta(db, {invoice_id}).get(invoice_id)
    return {"status": "OK", **_to_dict(wb, meta)}


def update_waybill(db: Session, waybill_id: int, fields: dict) -> dict:
    wb = db.get(Waybill, waybill_id)
    if wb is None:
        return {"status": "NOT_FOUND"}
    for k in _EDITABLE:
        if k in fields and fields[k] is not None:
            setattr(wb, k, fields[k])
    new_status = fields.get("status")
    if new_status is not None:
        if new_status not in WAYBILL_STATUSES:
            return {"status": "ERROR", "error": f"invalid status '{new_status}'"}
        wb.status = new_status
        # Stamp the send time the first time it moves to dispatched.
        if new_status in ("DISPATCHED", "DELIVERED") and wb.dispatched_at is None:
            wb.dispatched_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(wb)
    meta = _invoice_meta(db, {wb.invoice_id}).get(wb.invoice_id)
    creator = _user_names(db, {wb.created_by_user_id}).get(wb.created_by_user_id)
    return {"status": "OK", **_to_dict(wb, meta, creator)}


def get_waybill(db: Session, waybill_id: int) -> dict | None:
    wb = db.get(Waybill, waybill_id)
    if wb is None:
        return None
    meta = _invoice_meta(db, {wb.invoice_id}).get(wb.invoice_id)
    creator = _user_names(db, {wb.created_by_user_id}).get(wb.created_by_user_id)
    return _to_dict(wb, meta, creator)


def list_waybills(db: Session, *, status: str | None = None, invoice_id: int | None = None,
                  customer_id: int | None = None, q: str | None = None,
                  limit: int = 50, offset: int = 0) -> dict:
    stmt = select(Waybill)
    if status:
        stmt = stmt.where(Waybill.status == status)
    if invoice_id is not None:
        stmt = stmt.where(Waybill.invoice_id == invoice_id)
    if q:
        stmt = stmt.where(Waybill.waybill_number.ilike(f"%{q}%"))
    if customer_id is not None:
        stmt = stmt.where(Waybill.invoice_id.in_(
            select(Invoice.id).where(Invoice.customer_id == customer_id)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(Waybill.id.desc()).limit(limit).offset(offset)
    ).all()
    meta = _invoice_meta(db, {w.invoice_id for w in rows})
    creators = _user_names(db, {w.created_by_user_id for w in rows})
    return {
        "items": [_to_dict(w, meta.get(w.invoice_id), creators.get(w.created_by_user_id))
                  for w in rows],
        "total": int(total or 0), "limit": limit, "offset": offset,
    }
