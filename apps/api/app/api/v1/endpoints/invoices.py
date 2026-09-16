from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, Role, VerificationStatus
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceLine, InvoiceVersion
from app.models.user import User
from app.schemas.entities import InvoiceCreate, InvoiceOut
from app.services import audit, stock

router = APIRouter(tags=["invoices"])

_TOLERANCE = 0.01  # currency rounding tolerance for arithmetic validation
_SORTABLE = {"invoice_number", "invoice_date", "total", "subtotal", "tax", "id"}


def _snapshot(inv: Invoice) -> dict:
    """A complete, immutable picture of an invoice for the version history."""
    return {
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
        "customer_id": inv.customer_id,
        "currency": inv.currency,
        "subtotal": float(inv.subtotal or 0),
        "discount": float(inv.discount or 0),
        "tax": float(inv.tax or 0),
        "shipping": float(inv.shipping or 0),
        "shipping_note": inv.shipping_note,
        "total": float(inv.total or 0),
        "verification_status": inv.verification_status,
        "lines": [
            {"product_id": ln.product_id, "description": ln.original_description,
             "quantity": float(ln.quantity or 0), "unit_price": float(ln.unit_price or 0),
             "line_total": float(ln.line_total or 0)}
            for ln in inv.lines
        ],
    }


def _record_version(db: Session, inv: Invoice, user_id: int | None, note: str) -> None:
    db.add(InvoiceVersion(
        invoice_id=inv.id, version_no=inv.version_no, snapshot=_snapshot(inv),
        changed_by_user_id=user_id, change_note=note,
    ))


def _user_names(db: Session) -> dict[int, str]:
    return {
        u.id: (u.full_name or u.email)
        for u in db.query(User.id, User.full_name, User.email).all()
    }


@router.get("")
def list_invoices(
    db: Session = Depends(db_session),
    _: User = Depends(get_current_user),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    customer_id: int | None = None,
    q: str | None = Query(None, description="search invoice number"),
    verification_status: str | None = Query(None),
    payment_status: str | None = Query(None, description="UNPAID | PARTIAL | PAID"),
    sort: str | None = Query(None),
    sort_dir: str = Query("asc"),
) -> dict:
    stmt = select(Invoice).options(selectinload(Invoice.lines))
    if customer_id is not None:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if q:
        stmt = stmt.where(Invoice.invoice_number.ilike(f"%{q}%"))
    if verification_status:
        stmt = stmt.where(Invoice.verification_status == verification_status)
    if payment_status:
        stmt = stmt.where(Invoice.payment_status == payment_status)
    col = getattr(Invoice, sort) if sort in _SORTABLE else Invoice.id
    stmt = stmt.order_by(col.desc() if sort_dir == "desc" else col.asc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    names = _user_names(db)
    cust_ids = {r.customer_id for r in rows if r.customer_id}
    cust_names = {
        cid: cname for cid, cname in db.execute(
            select(Customer.id, Customer.name).where(Customer.id.in_(cust_ids))
        ).all()
    } if cust_ids else {}
    items = []
    for r in rows:
        d = InvoiceOut.model_validate(r).model_dump(mode="json")
        d["created_by"] = names.get(r.created_by_user_id)
        d["version_no"] = r.version_no
        d["customer_name"] = cust_names.get(r.customer_id)
        d["balance"] = round(float(r.total or 0) - float(r.amount_paid or 0), 2)
        items.append(d)
    return {
        "items": items,
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
        "sortable_fields": sorted(_SORTABLE),
    }


@router.get("/{invoice_id}")
def get_invoice(
    invoice_id: int, db: Session = Depends(db_session), _: User = Depends(get_current_user)
) -> dict:
    obj = db.get(Invoice, invoice_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Invoice {invoice_id} not found")
    names = _user_names(db)
    cust = db.get(Customer, obj.customer_id) if obj.customer_id else None
    d = InvoiceOut.model_validate(obj).model_dump(mode="json")
    from app.services import receivables
    d.update({
        "customer_name": cust.name if cust else None,
        "created_by": names.get(obj.created_by_user_id),
        "updated_by": names.get(obj.updated_by_user_id),
        "version_no": obj.version_no,
        "version_count": db.scalar(
            select(func.count()).select_from(InvoiceVersion)
            .where(InvoiceVersion.invoice_id == invoice_id)
        ) or 0,
        # Payment history with who recorded each (accounts-receivable traceability).
        "balance": round(float(obj.total or 0) - float(obj.amount_paid or 0), 2),
        "payments": receivables.list_payments(db, invoice_id),
    })
    return d


@router.get("/{invoice_id}/versions")
def invoice_versions(
    invoice_id: int, db: Session = Depends(db_session), _: User = Depends(get_current_user)
) -> dict:
    if db.get(Invoice, invoice_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Invoice {invoice_id} not found")
    names = _user_names(db)
    rows = db.scalars(
        select(InvoiceVersion).where(InvoiceVersion.invoice_id == invoice_id)
        .order_by(InvoiceVersion.version_no.desc())
    ).all()
    return {
        "items": [
            {"version_no": v.version_no, "snapshot": v.snapshot,
             "changed_by": names.get(v.changed_by_user_id), "change_note": v.change_note,
             "changed_at": v.created_at.isoformat() if v.created_at else None}
            for v in rows
        ],
        "provenance": "REAL",
    }


class PatchLine(BaseModel):
    product_id: int | None = None
    original_description: str | None = None
    quantity: float = 0
    unit_price: float = 0


class InvoicePatch(BaseModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    customer_id: int | None = None
    tax: float | None = None
    discount: float | None = None
    shipping: float | None = None
    shipping_note: str | None = None
    verification_status: str | None = None
    lines: list[PatchLine] | None = None
    change_note: str | None = None


_HEADER_FIELDS = ("invoice_number", "invoice_date", "customer_id", "tax", "discount",
                  "shipping", "shipping_note", "verification_status")


@router.patch("/{invoice_id}")
def update_invoice(
    invoice_id: int,
    payload: InvoicePatch,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.MANAGER)),
) -> dict:
    """Edit an invoice — header fields and/or its full line items. Every edit keeps
    the prior state as an immutable version, so nothing is ever lost."""
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Invoice {invoice_id} not found")

    data = payload.model_dump(exclude_unset=True)
    fields = {k: data[k] for k in _HEADER_FIELDS if k in data}
    if not fields and payload.lines is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no changes supplied")
    old = {k: getattr(inv, k) for k in fields}
    for k, v in fields.items():
        setattr(inv, k, v)

    # Replace the line items when supplied, recomputing the subtotal from them.
    if payload.lines is not None:
        inv.lines.clear()
        for ln in payload.lines:
            inv.lines.append(InvoiceLine(
                product_id=ln.product_id, original_description=ln.original_description,
                quantity=ln.quantity, unit_price=ln.unit_price,
                line_total=round(ln.quantity * ln.unit_price, 2),
            ))
        inv.subtotal = round(sum(ln.quantity * ln.unit_price for ln in payload.lines), 2)

    inv.total = round(float(inv.subtotal or 0) + float(inv.tax or 0) + float(inv.shipping or 0)
                     - float(inv.discount or 0), 2)
    inv.updated_by_user_id = user.id
    inv.version_no += 1
    db.flush()
    _record_version(db, inv, user.id, payload.change_note or "edited")
    db.commit()
    db.refresh(inv)
    audit.record(
        db, action=AuditAction.UPDATE, user_id=user.id, entity_type="invoice",
        entity_id=inv.id,
        old_value={k: str(v) for k, v in old.items()},
        new_value={k: str(v) for k, v in fields.items()} | (
            {"lines": len(payload.lines)} if payload.lines is not None else {}),
        summary=f"invoice {inv.invoice_number} edited to v{inv.version_no}",
    )
    return get_invoice(inv.id, db, user)


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF)),
) -> Invoice:
    computed_subtotal = round(sum(line.line_total for line in payload.lines), 2)
    total = round(computed_subtotal + payload.tax - payload.discount, 2)

    # Arithmetic validation (spec §13): flag rather than silently correct.
    warnings: list[str] = []
    verification = VerificationStatus.VERIFIED.value
    for i, line in enumerate(payload.lines):
        expected = round(line.quantity * line.unit_price, 2)
        if abs(expected - line.line_total) > _TOLERANCE:
            warnings.append(
                f"Line {i + 1}: quantity*unit_price={expected} != line_total={line.line_total}"
            )
    if warnings:
        verification = VerificationStatus.NEEDS_REVIEW.value

    invoice = Invoice(
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        customer_id=payload.customer_id,
        branch_id=payload.branch_id,
        currency=payload.currency,
        subtotal=computed_subtotal,
        discount=payload.discount,
        tax=payload.tax,
        total=total,
        verification_status=verification,
        source_reference="; ".join(warnings) if warnings else None,
        created_by_user_id=user.id,
        version_no=1,
    )
    for line in payload.lines:
        invoice.lines.append(
            InvoiceLine(
                product_id=line.product_id,
                original_description=line.original_description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
                unit_cost=line.unit_cost,
                verification_status=verification,
            )
        )
    db.add(invoice)
    db.flush()
    _record_version(db, invoice, user.id, "created")
    db.commit()
    db.refresh(invoice)
    audit.record(
        db,
        action=AuditAction.CREATE,
        user_id=user.id,
        entity_type="invoice",
        entity_id=invoice.id,
        new_value={"invoice_number": invoice.invoice_number, "total": str(total)},
        summary="; ".join(warnings) if warnings else "invoice created",
    )
    return invoice


# --------------------------------------------------------------------------- #
# Sell — an invoice that MOVES stock: it draws each line from a warehouse (FIFO)
# and records who bought which lot. This is the connected point of sale.
# --------------------------------------------------------------------------- #
class SellLine(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: float
    original_description: str | None = None


class SellRequest(BaseModel):
    invoice_number: str
    invoice_date: date
    warehouse_id: int
    customer_id: int | None = None
    currency: str = "NGN"
    discount: float = 0
    tax: float = 0
    shipping: float = 0
    shipping_note: str | None = None
    lines: list[SellLine] = Field(min_length=1)


@router.post("/sell", status_code=status.HTTP_201_CREATED)
def sell(
    payload: SellRequest,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF)),
) -> dict:
    """Create an invoice and fulfil it from a warehouse's stock, decrementing lots
    (FIFO) and tagging each movement with the buyer."""
    subtotal = round(sum(ln.quantity * ln.unit_price for ln in payload.lines), 2)
    total = round(subtotal + payload.tax + payload.shipping - payload.discount, 2)

    # Payment due date from the customer's credit terms (if any); else due at sale.
    due_date = payload.invoice_date
    if payload.customer_id is not None:
        cust = db.get(Customer, payload.customer_id)
        if cust is not None and cust.payment_terms_days:
            from datetime import timedelta
            due_date = payload.invoice_date + timedelta(days=int(cust.payment_terms_days))

    invoice = Invoice(
        invoice_number=payload.invoice_number, invoice_date=payload.invoice_date,
        customer_id=payload.customer_id, currency=payload.currency,
        subtotal=subtotal, discount=payload.discount, tax=payload.tax,
        shipping=payload.shipping, shipping_note=payload.shipping_note, total=total,
        due_date=due_date,
        verification_status=VerificationStatus.VERIFIED.value,
        created_by_user_id=user.id, version_no=1,
    )
    db.add(invoice)
    db.flush()  # assign invoice.id for the stock movements

    allocations: list[dict] = []
    try:
        for ln in payload.lines:
            allocs = stock.allocate_for_sale(
                db, product_id=ln.product_id, warehouse_id=payload.warehouse_id,
                quantity=ln.quantity, invoice_id=invoice.id, customer_id=payload.customer_id,
                user_id=user.id, commit=False,
            )
            # Weighted-average landed cost from the lots consumed = COGS basis.
            qty = sum(a["quantity"] for a in allocs)
            cost = sum((a["unit_cost"] or 0) * a["quantity"] for a in allocs)
            avg_cost = round(cost / qty, 2) if qty else None
            invoice.lines.append(InvoiceLine(
                product_id=ln.product_id, original_description=ln.original_description,
                quantity=ln.quantity, unit_price=ln.unit_price,
                line_total=round(ln.quantity * ln.unit_price, 2), unit_cost=avg_cost,
                verification_status=VerificationStatus.VERIFIED.value,
            ))
            allocations.append({"product_id": ln.product_id, "lots": allocs})
    except stock.StockError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    _record_version(db, invoice, user.id, "sale created")
    db.commit()
    db.refresh(invoice)
    audit.record(
        db, action=AuditAction.CREATE, user_id=user.id, entity_type="invoice",
        entity_id=invoice.id,
        new_value={"invoice_number": invoice.invoice_number, "total": str(total),
                   "warehouse_id": payload.warehouse_id},
        summary=f"sale invoice {invoice.invoice_number} fulfilled from warehouse "
                f"{payload.warehouse_id}",
    )
    return {
        "invoice": InvoiceOut.model_validate(invoice).model_dump(mode="json"),
        "allocations": allocations,
        "note": "Stock drawn FIFO from the warehouse; each unit traces to its lot and buyer.",
    }
