"""Accounts-receivable API: record customer payments, report who owes what."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_role
from app.core.enums import Role
from app.models.user import User
from app.services import receivables

router = APIRouter(tags=["receivables"], prefix="/receivables")


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    method: str = Field("cash", max_length=32)
    paid_at: date | None = None
    reference: str | None = Field(None, max_length=128)
    note: str | None = Field(None, max_length=255)


@router.post("/invoices/{invoice_id}/payments")
def record_payment(
    invoice_id: int,
    payload: PaymentIn,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF)),
) -> dict:
    """Record a payment a customer made against an invoice."""
    r = receivables.record_payment(
        db, invoice_id=invoice_id, amount=payload.amount, method=payload.method,
        paid_at=payload.paid_at, reference=payload.reference, note=payload.note,
        user_id=user.id,
    )
    if r["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, r["error"])
    if r["status"] == "ERROR":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, r["error"])
    return r


@router.get("/invoices/{invoice_id}/payments")
def invoice_payments(
    invoice_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    return {"items": receivables.list_payments(db, invoice_id)}


@router.post("/payments/{payment_id}/void")
def void_payment(
    payment_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.MANAGER)),
) -> dict:
    r = receivables.void_payment(db, payment_id)
    if r["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "payment not found")
    return r


@router.get("/summary")
def summary(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    """Total outstanding, aging buckets and top debtors."""
    return receivables.receivables_summary(db)


@router.get("/overdue")
def overdue(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    return receivables.overdue_invoices(db)


@router.get("/customers/{customer_id}/statement")
def statement(
    customer_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    r = receivables.customer_statement(db, customer_id)
    if r.get("status") == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found")
    return r
