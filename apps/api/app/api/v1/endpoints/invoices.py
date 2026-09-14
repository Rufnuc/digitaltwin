from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, Role, VerificationStatus
from app.models.invoice import Invoice, InvoiceLine
from app.models.user import User
from app.schemas.entities import InvoiceCreate, InvoiceOut
from app.services import audit, stock

router = APIRouter(tags=["invoices"])

_TOLERANCE = 0.01  # currency rounding tolerance for arithmetic validation


@router.get("")
def list_invoices(
    db: Session = Depends(db_session),
    _: User = Depends(get_current_user),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    customer_id: int | None = None,
) -> dict:
    stmt = select(Invoice).options(selectinload(Invoice.lines))
    if customer_id is not None:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Invoice.id).limit(limit).offset(offset)).all()
    return {
        "items": [InvoiceOut.model_validate(r).model_dump(mode="json") for r in rows],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: int, db: Session = Depends(db_session), _: User = Depends(get_current_user)
) -> Invoice:
    obj = db.get(Invoice, invoice_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Invoice {invoice_id} not found")
    return obj


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
    total = round(subtotal + payload.tax - payload.discount, 2)

    invoice = Invoice(
        invoice_number=payload.invoice_number, invoice_date=payload.invoice_date,
        customer_id=payload.customer_id, currency=payload.currency,
        subtotal=subtotal, discount=payload.discount, tax=payload.tax, total=total,
        verification_status=VerificationStatus.VERIFIED.value,
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
