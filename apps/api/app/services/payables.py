"""Accounts payable: record payments to suppliers and report what we owe.

Mirror of the receivables service on the supplier side. A purchase's amount_paid /
payment_status are kept in step with its confirmed supplier payments here.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.purchase import Purchase, SupplierPayment
from app.models.supplier import Supplier

_EPS = 0.01


def _recalc(db: Session, purchase: Purchase) -> None:
    # amount_paid is denominated in the purchase's own currency, so only payments
    # made in that currency net against the balance. Foreign-currency payments are
    # still recorded (for the audit trail) but don't move the naira/base balance.
    pur_ccy = (purchase.currency or "NGN").upper()
    paid = float(db.scalar(
        select(func.coalesce(func.sum(SupplierPayment.amount), 0)).where(
            SupplierPayment.purchase_id == purchase.id,
            SupplierPayment.status == "CONFIRMED",
            func.upper(func.coalesce(SupplierPayment.currency, "NGN")) == pur_ccy,
        )
    ) or 0.0)
    purchase.amount_paid = round(paid, 2)
    total = float(purchase.total or 0)
    if paid >= total - _EPS and total > 0:
        purchase.payment_status = "PAID"
    elif paid > _EPS:
        purchase.payment_status = "PARTIAL"
    else:
        purchase.payment_status = "UNPAID"


def balance(purchase: Purchase) -> float:
    return round(float(purchase.total or 0) - float(purchase.amount_paid or 0), 2)


def record_supplier_payment(db: Session, *, purchase_id: int, amount: float,
                            method: str = "transfer", paid_at: date | None = None,
                            reference: str | None = None, note: str | None = None,
                            currency: str | None = None,
                            user_id: int | None = None, txid: str | None = None,
                            from_account: str | None = None, from_name: str | None = None,
                            to_account: str | None = None, to_name: str | None = None) -> dict:
    pur = db.get(Purchase, purchase_id)
    if pur is None:
        return {"status": "NOT_FOUND", "error": f"purchase {purchase_id} not found"}
    amount = round(float(amount), 2)
    if amount <= 0:
        return {"status": "ERROR", "error": "amount must be positive"}
    # Default the payment currency to the purchase's own currency.
    ccy = (currency or pur.currency or "NGN").upper()[:3]
    # We only reconcile against the purchase balance when paying in the purchase's
    # own currency; a foreign-currency payment is recorded but not netted (rates vary).
    same_ccy = ccy == (pur.currency or "NGN").upper()
    if same_ccy:
        outstanding = balance(pur)
        if amount > outstanding + _EPS:
            return {"status": "ERROR",
                    "error": f"amount {amount} exceeds what we still owe ({outstanding})",
                    "outstanding": outstanding}
    pay = SupplierPayment(
        purchase_id=pur.id, supplier_id=pur.supplier_id, amount=amount, currency=ccy,
        method=method, paid_at=paid_at or date.today(), reference=reference, note=note,
        status="CONFIRMED", recorded_by_user_id=user_id, data_origin="REAL",
        txid=txid, from_account=from_account, from_name=from_name,
        to_account=to_account, to_name=to_name,
    )
    db.add(pay)
    db.flush()
    _recalc(db, pur)
    db.commit()
    db.refresh(pay)
    return {"status": "OK", "payment_id": pay.id, "purchase_id": pur.id,
            "amount": amount, "amount_paid": float(pur.amount_paid),
            "balance": balance(pur), "payment_status": pur.payment_status}


def _due(pur: Purchase) -> date:
    return pur.due_date or pur.purchase_date


def _open(db: Session, supplier_id: int | None = None) -> list[Purchase]:
    stmt = select(Purchase).where(Purchase.payment_status != "PAID")
    if supplier_id is not None:
        stmt = stmt.where(Purchase.supplier_id == supplier_id)
    return list(db.scalars(stmt).all())


def payables_summary(db: Session, as_of: date | None = None) -> dict:
    """Total we owe suppliers, aging buckets, and the biggest creditors."""
    as_of = as_of or date.today()
    buckets = {"current": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    per_supplier: dict[int | None, float] = {}
    total = 0.0
    for pur in _open(db):
        bal = balance(pur)
        if bal <= _EPS:
            continue
        total += bal
        d = max(0, (as_of - _due(pur)).days)
        key = ("current" if d == 0 else "1-30" if d <= 30 else "31-60" if d <= 60
               else "61-90" if d <= 90 else "90+")
        buckets[key] += bal
        per_supplier[pur.supplier_id] = per_supplier.get(pur.supplier_id, 0.0) + bal

    names = _supplier_names(db, {s for s in per_supplier if s is not None})
    creditors = sorted(
        ({"supplier_id": sid, "supplier_name": names.get(sid, "Unassigned"),
          "owed": round(v, 2)} for sid, v in per_supplier.items()),
        key=lambda d: d["owed"], reverse=True,
    )
    return {
        "as_of": as_of.isoformat(),
        "total_payable": round(total, 2),
        "overdue_total": round(total - buckets["current"], 2),
        "aging": {k: round(v, 2) for k, v in buckets.items()},
        "open_purchase_count": sum(1 for p in _open(db) if balance(p) > _EPS),
        "creditors": creditors[:20],
        "provenance": "REAL",
    }


def list_supplier_payments(db: Session, purchase_id: int) -> list[dict]:
    rows = db.scalars(select(SupplierPayment).where(
        SupplierPayment.purchase_id == purchase_id).order_by(SupplierPayment.id)).all()
    return [{"id": p.id, "amount": float(p.amount), "currency": p.currency or "NGN",
             "method": p.method, "reference": p.reference, "paid_at": p.paid_at.isoformat(),
             "status": p.status, "txid": p.txid, "from_account": p.from_account,
             "from_name": p.from_name, "to_account": p.to_account, "to_name": p.to_name}
            for p in rows]


def _supplier_names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {sid: name for sid, name in db.execute(
        select(Supplier.id, Supplier.name).where(Supplier.id.in_(ids))
    ).all()}
