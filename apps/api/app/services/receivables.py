"""Accounts receivable: record customer payments and report who owes what.

An invoice's ``amount_paid`` / ``payment_status`` are kept in step with its confirmed
payments here (the single place that mutates them), so balances are always correct.
Everything money-related is REAL data; the reports (aging, debtors) are derived.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.payment import Payment

_EPS = 0.01  # naira rounding tolerance


def _recalc(db: Session, invoice: Invoice) -> None:
    """Refresh amount_paid + payment_status from the invoice's confirmed payments."""
    paid = float(db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.invoice_id == invoice.id, Payment.status == "CONFIRMED"
        )
    ) or 0.0)
    invoice.amount_paid = round(paid, 2)
    total = float(invoice.total or 0)
    if paid >= total - _EPS and total > 0:
        invoice.payment_status = "PAID"
    elif paid > _EPS:
        invoice.payment_status = "PARTIAL"
    else:
        invoice.payment_status = "UNPAID"


def balance(invoice: Invoice) -> float:
    return round(float(invoice.total or 0) - float(invoice.amount_paid or 0), 2)


def record_payment(db: Session, *, invoice_id: int, amount: float, method: str = "cash",
                   paid_at: date | None = None, reference: str | None = None,
                   note: str | None = None, user_id: int | None = None,
                   txid: str | None = None, from_account: str | None = None,
                   from_name: str | None = None, to_account: str | None = None,
                   to_name: str | None = None, idempotency_key: str | None = None) -> dict:
    """Record a customer payment against an invoice. Rejects non-positive amounts
    and overpayment beyond the outstanding balance.

    The invoice row is locked for the balance check + status recompute so two
    concurrent payments cannot both pass the overpayment guard. An idempotency key
    makes a retried/double-tapped submit return the original result rather than
    recording the payment twice.
    """
    from app.services import idempotency
    res = idempotency.reserve(db, idempotency_key, scope="record_payment")
    if res.replay is not None:
        return res.replay
    if res.in_progress:
        return {"status": "ERROR", "error": "an identical payment is already being processed"}

    # Lock the invoice row: the balance we validate against cannot shift under us.
    inv = db.get(Invoice, invoice_id, with_for_update=True)
    if inv is None:
        db.rollback()
        return {"status": "NOT_FOUND", "error": f"invoice {invoice_id} not found"}
    amount = round(float(amount), 2)
    if amount <= 0:
        db.rollback()
        return {"status": "ERROR", "error": "amount must be positive"}
    outstanding = balance(inv)
    if amount > outstanding + _EPS:
        db.rollback()
        return {"status": "ERROR",
                "error": f"amount {amount} exceeds the outstanding balance {outstanding}",
                "outstanding": outstanding}

    pay = Payment(
        invoice_id=inv.id, customer_id=inv.customer_id, amount=amount, method=method,
        paid_at=paid_at or date.today(), reference=reference, note=note,
        status="CONFIRMED", recorded_by_user_id=user_id, data_origin="REAL",
        txid=txid, from_account=from_account, from_name=from_name,
        to_account=to_account, to_name=to_name,
    )
    db.add(pay)
    db.flush()
    _recalc(db, inv)
    result = {
        "status": "OK", "payment_id": pay.id, "invoice_id": inv.id,
        "amount": amount, "invoice_total": float(inv.total or 0),
        "amount_paid": float(inv.amount_paid), "balance": balance(inv),
        "payment_status": inv.payment_status,
    }
    # complete() commits the payment, the status recompute and the idempotency row
    # together; with no key it is a no-op so we commit here.
    if idempotency_key:
        idempotency.complete(db, idempotency_key, result)
    else:
        db.commit()
    db.refresh(pay)
    return result


def void_payment(db: Session, payment_id: int) -> dict:
    pay = db.get(Payment, payment_id)
    if pay is None:
        return {"status": "NOT_FOUND"}
    pay.status = "VOIDED"
    db.flush()
    inv = db.get(Invoice, pay.invoice_id)
    if inv is not None:
        _recalc(db, inv)
    db.commit()
    return {"status": "OK", "payment_id": payment_id,
            "invoice_balance": balance(inv) if inv else None}


def list_payments(db: Session, invoice_id: int) -> list[dict]:
    rows = db.scalars(
        select(Payment).where(Payment.invoice_id == invoice_id).order_by(Payment.id)
    ).all()
    names = _user_names(db, {p.recorded_by_user_id for p in rows if p.recorded_by_user_id})
    return [{
        "id": p.id, "amount": float(p.amount), "method": p.method,
        "reference": p.reference, "paid_at": p.paid_at.isoformat(),
        "status": p.status, "note": p.note,
        "recorded_by": names.get(p.recorded_by_user_id),
        "recorded_at": p.created_at.isoformat() if p.created_at else None,
        "txid": p.txid, "from_account": p.from_account, "from_name": p.from_name,
        "to_account": p.to_account, "to_name": p.to_name,
    } for p in rows]


def _user_names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    from app.models.user import User
    return {uid: (name or email) for uid, name, email in db.execute(
        select(User.id, User.full_name, User.email).where(User.id.in_(ids))
    ).all()}


def _due(inv: Invoice) -> date:
    return inv.due_date or inv.invoice_date


def _days_overdue(inv: Invoice, as_of: date) -> int:
    return max(0, (as_of - _due(inv)).days)


def _open_invoices(db: Session, customer_id: int | None = None) -> list[Invoice]:
    stmt = select(Invoice).where(
        Invoice.payment_status != "PAID", Invoice.voided_at.is_(None)
    )
    if customer_id is not None:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    return list(db.scalars(stmt).all())


def customer_balance(db: Session, customer_id: int) -> float:
    return round(sum(balance(i) for i in _open_invoices(db, customer_id)), 2)


def receivables_summary(db: Session, as_of: date | None = None) -> dict:
    """Total outstanding, aging buckets, and the top debtors."""
    as_of = as_of or date.today()
    buckets = {"current": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    per_customer: dict[int | None, float] = {}
    total = 0.0
    open_invoices = _open_invoices(db)
    for inv in open_invoices:
        bal = balance(inv)
        if bal <= _EPS:
            continue
        total += bal
        d = _days_overdue(inv, as_of)
        key = ("current" if d == 0 else "1-30" if d <= 30 else "31-60" if d <= 60
               else "61-90" if d <= 90 else "90+")
        buckets[key] += bal
        per_customer[inv.customer_id] = per_customer.get(inv.customer_id, 0.0) + bal

    names = _customer_names(db, {c for c in per_customer if c is not None})
    debtors = sorted(
        ({"customer_id": cid, "customer_name": names.get(cid, "Walk-in / unassigned"),
          "outstanding": round(bal, 2)} for cid, bal in per_customer.items()),
        key=lambda d: d["outstanding"], reverse=True,
    )
    overdue_total = round(total - buckets["current"], 2)
    return {
        "as_of": as_of.isoformat(),
        "total_outstanding": round(total, 2),
        "overdue_total": overdue_total,
        "aging": {k: round(v, 2) for k, v in buckets.items()},
        "open_invoice_count": sum(1 for i in open_invoices if balance(i) > _EPS),
        "debtors": debtors[:20],
        "provenance": "REAL",
    }


def overdue_invoices(db: Session, as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    rows = []
    for inv in _open_invoices(db):
        bal = balance(inv)
        d = _days_overdue(inv, as_of)
        if bal > _EPS and d > 0:
            rows.append({"invoice_id": inv.id, "invoice_number": inv.invoice_number,
                         "customer_id": inv.customer_id, "balance": bal,
                         "days_overdue": d, "due": _due(inv).isoformat()})
    rows.sort(key=lambda r: r["days_overdue"], reverse=True)
    names = _customer_names(db, {r["customer_id"] for r in rows if r["customer_id"]})
    for r in rows:
        r["customer_name"] = names.get(r["customer_id"], "Walk-in / unassigned")
    return {"as_of": as_of.isoformat(), "count": len(rows),
            "total": round(sum(r["balance"] for r in rows), 2), "invoices": rows[:50]}


def customer_statement(db: Session, customer_id: int) -> dict:
    """A customer's invoices and payments as one running-balance timeline."""
    cust = db.get(Customer, customer_id)
    if cust is None:
        return {"status": "NOT_FOUND"}
    invoices = db.scalars(
        select(Invoice).where(Invoice.customer_id == customer_id, Invoice.voided_at.is_(None))
        .order_by(Invoice.invoice_date, Invoice.id)
    ).all()
    events = []
    for inv in invoices:
        events.append({"date": inv.invoice_date.isoformat(), "type": "INVOICE",
                       "ref": inv.invoice_number, "charge": float(inv.total or 0),
                       "payment": 0.0})
        for p in db.scalars(select(Payment).where(
                Payment.invoice_id == inv.id, Payment.status == "CONFIRMED"
        ).order_by(Payment.paid_at, Payment.id)).all():
            events.append({"date": p.paid_at.isoformat(), "type": "PAYMENT",
                           "ref": p.reference or p.method, "charge": 0.0,
                           "payment": float(p.amount)})
    events.sort(key=lambda e: e["date"])
    running = 0.0
    for e in events:
        running += e["charge"] - e["payment"]
        e["balance"] = round(running, 2)
    return {
        "customer_id": customer_id, "customer_name": cust.name,
        "credit_limit": float(cust.credit_limit) if cust.credit_limit else None,
        "outstanding": customer_balance(db, customer_id),
        "events": events,
    }


def _customer_names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {cid: name for cid, name in db.execute(
        select(Customer.id, Customer.name).where(Customer.id.in_(ids))
    ).all()}
