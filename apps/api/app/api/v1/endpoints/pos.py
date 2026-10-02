from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import Role
from app.models.invoice import Invoice
from app.models.user import User
from app.services.pos import reconcile
from app.services.pos.base import PosProviderError, get_pos_provider

router = APIRouter(tags=["pos"])


class ExpectIn(BaseModel):
    invoice_id: int
    amount: float = Field(gt=0)
    terminal_id: str | None = None


class ChargeIn(ExpectIn):
    terminal_id: str  # required to push to a specific terminal


class AssignIn(BaseModel):
    invoice_id: int


def _require_invoice(db: Session, invoice_id: int) -> Invoice:
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Invoice {invoice_id} not found")
    if inv.voided_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "invoice is void")
    return inv


@router.post("/pos/expect")
def expect_payment(
    payload: ExpectIn,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF, allow=(Role.SALESGIRL,))),
) -> dict:
    """Tell the system a customer is about to pay this amount on a POS terminal, so the
    incoming transaction links to this invoice automatically (full or partial)."""
    _require_invoice(db, payload.invoice_id)
    exp = reconcile.create_expected(
        db, invoice_id=payload.invoice_id, amount=payload.amount,
        terminal_id=payload.terminal_id, user_id=user.id,
    )
    return {"status": "OK", "expected_id": exp.id, "expires_at": exp.expires_at.isoformat()}


@router.post("/pos/charge")
def charge_terminal(
    payload: ChargeIn,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF, allow=(Role.SALESGIRL,))),
) -> dict:
    """Push the amount to the Moniepoint terminal so it pops up ready to collect, and
    record the expectation so the resulting transaction links back automatically."""
    inv = _require_invoice(db, payload.invoice_id)
    exp = reconcile.create_expected(
        db, invoice_id=payload.invoice_id, amount=payload.amount,
        terminal_id=payload.terminal_id, user_id=user.id, commit=False,
    )
    provider = get_pos_provider()
    pushed, message, request_id = False, None, None
    if getattr(provider, "can_push", False):
        try:
            res = provider.push_charge(
                terminal_id=payload.terminal_id, amount=payload.amount,
                reference=inv.invoice_number,
            )
            pushed, request_id = True, res.get("request_id")
        except PosProviderError as e:
            message = str(e)
    else:
        message = ("Terminal push isn't configured — the amount was not sent to the "
                   "terminal, but it will still reconcile automatically when charged.")
    exp.provider = provider.name
    exp.provider_request_id = request_id
    exp.pushed = pushed
    db.commit()
    db.refresh(exp)
    return {"status": "OK", "expected_id": exp.id, "pushed": pushed, "message": message}


@router.get("/pos/unmatched")
def unmatched(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF, allow=(Role.SALESGIRL,))),
) -> dict:
    return {"items": reconcile.list_unmatched(db)}


@router.post("/pos/transactions/{txn_id}/assign")
def assign(
    txn_id: int,
    payload: AssignIn,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF, allow=(Role.SALESGIRL,))),
) -> dict:
    r = reconcile.assign_transaction(db, txn_id=txn_id, invoice_id=payload.invoice_id,
                                     user_id=user.id)
    if r["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "transaction not found")
    if r["status"] == "ERROR":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, r.get("error", "could not assign"))
    return r


@router.post("/pos/transactions/{txn_id}/ignore")
def ignore(
    txn_id: int,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.MANAGER, allow=(Role.SALESGIRL,))),
) -> dict:
    r = reconcile.ignore_transaction(db, txn_id=txn_id, user_id=user.id)
    if r["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "transaction not found")
    if r["status"] == "ERROR":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, r.get("error", "could not ignore"))
    return r


@router.post("/webhooks/pos/{provider_name}")
async def pos_webhook(
    provider_name: str, request: Request, db: Session = Depends(db_session)
) -> dict:
    """Receive a terminal transaction from the POS provider. Signature-verified and
    idempotent; unauthenticated (the signature is the trust)."""
    provider = get_pos_provider()
    if provider.name != provider_name or provider.name == "none":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown or disabled POS provider")
    body = await request.body()
    if not provider.verify_webhook(body, dict(request.headers)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid webhook signature")
    try:
        payload = json.loads(body.decode() or "{}")
        txn = provider.parse_webhook(payload)
    except (ValueError, PosProviderError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"bad webhook payload: {e}") from None
    row = reconcile.ingest_transaction(db, txn)
    return {"status": "OK", "transaction_id": row.id, "matched": row.status == "MATCHED"}
