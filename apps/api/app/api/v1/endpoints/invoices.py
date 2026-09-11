from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, Role, VerificationStatus
from app.models.invoice import Invoice, InvoiceLine
from app.models.user import User
from app.schemas.entities import InvoiceCreate, InvoiceOut
from app.services import audit

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
