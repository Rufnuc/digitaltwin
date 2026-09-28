"""Accounts-payable API: record payments to suppliers, report what we owe."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_role
from app.core.enums import Role
from app.models.user import User
from app.services import payables

router = APIRouter(tags=["payables"], prefix="/payables")


class SupplierPaymentIn(BaseModel):
    amount: float = Field(gt=0)
    currency: str | None = Field(None, max_length=3)
    method: str = Field("transfer", max_length=32)
    paid_at: date | None = None
    reference: str | None = Field(None, max_length=128)
    note: str | None = Field(None, max_length=255)
    txid: str | None = Field(None, max_length=128)
    from_account: str | None = Field(None, max_length=64)
    from_name: str | None = Field(None, max_length=128)
    to_account: str | None = Field(None, max_length=64)
    to_name: str | None = Field(None, max_length=128)


@router.post("/purchases/{purchase_id}/payments")
def record_payment(
    purchase_id: int,
    payload: SupplierPaymentIn,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.MANAGER)),
) -> dict:
    """Record a payment we made to a supplier against a purchase."""
    r = payables.record_supplier_payment(
        db, purchase_id=purchase_id, amount=payload.amount, method=payload.method,
        currency=payload.currency, paid_at=payload.paid_at, reference=payload.reference,
        note=payload.note, user_id=user.id, txid=payload.txid, from_account=payload.from_account,
        from_name=payload.from_name, to_account=payload.to_account,
        to_name=payload.to_name,
    )
    if r["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, r["error"])
    if r["status"] == "ERROR":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, r["error"])
    return r


@router.get("/summary")
def summary(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.MANAGER)),
) -> dict:
    """Total owed to suppliers, aging, and the biggest creditors."""
    return payables.payables_summary(db)


@router.get("/purchases/{purchase_id}/payments")
def purchase_payments(
    purchase_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.MANAGER)),
) -> dict:
    return {"items": payables.list_supplier_payments(db, purchase_id)}
