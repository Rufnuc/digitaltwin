"""POS reconciliation engine: expectations, auto-matching, manual assignment, and
ranked suggestions for unmatched transactions.

Matching strategy (best → fallback):
  1. An ExpectedPosPayment the cashier created when charging (amount + terminal +
     time) — reliable for full AND partial payments.
  2. A single open invoice whose outstanding balance equals the amount within the
     time window (unambiguous full payment).
  3. Otherwise UNMATCHED, surfaced with ranked suggestions for one-tap assignment.

The suggestion ranker is a transparent, feature-based score today. Every manual
assignment is a labelled example (transaction features → chosen invoice), so this is
the on-ramp to a learned ranker later (see `suggestion_features`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.pos import ExpectedPosPayment, PosTransaction
from app.services import receivables
from app.services.pos.base import PosTxn

_EPS = 0.01


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_expected(db: Session, *, invoice_id: int, amount: float,
                    terminal_id: str | None, user_id: int | None,
                    commit: bool = True) -> ExpectedPosPayment:
    exp = ExpectedPosPayment(
        invoice_id=invoice_id, amount=round(float(amount), 2), terminal_id=terminal_id,
        status="PENDING", created_by_user_id=user_id,
        expires_at=_now() + timedelta(minutes=settings.POS_EXPECT_TTL_MINUTES),
    )
    db.add(exp)
    if commit:
        db.commit()
        db.refresh(exp)
    return exp


def _expire_stale(db: Session) -> None:
    """Mark long-open expectations EXPIRED so they stop matching."""
    now = _now()
    for exp in db.scalars(
        select(ExpectedPosPayment).where(
            ExpectedPosPayment.status == "PENDING", ExpectedPosPayment.expires_at < now
        )
    ).all():
        exp.status = "EXPIRED"


def _record_payment_for(db: Session, invoice_id: int, amount: float, *, user_id: int | None,
                        reference: str | None) -> dict:
    return receivables.record_payment(
        db, invoice_id=invoice_id, amount=amount, method="pos",
        reference=reference, user_id=user_id, note="POS reconciliation",
    )


def ingest_transaction(db: Session, txn: PosTxn, *, auto: bool = True) -> PosTransaction:
    """Store a provider transaction (idempotent) and try to auto-match it."""
    existing = db.scalar(
        select(PosTransaction).where(
            PosTransaction.provider == txn.provider,
            PosTransaction.provider_txn_id == txn.provider_txn_id,
        )
    )
    if existing is not None:
        return existing  # retransmitted webhook — never double-count

    row = PosTransaction(
        provider=txn.provider, provider_txn_id=txn.provider_txn_id,
        terminal_id=txn.terminal_id, amount=round(float(txn.amount), 2),
        reference=txn.reference, masked_pan=txn.masked_pan,
        occurred_at=txn.occurred_at or _now(), status="UNMATCHED", raw=txn.raw or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if auto:
        _try_auto_match(db, row)
    return row


def _try_auto_match(db: Session, row: PosTransaction) -> None:
    _expire_stale(db)
    db.commit()
    amt = float(row.amount)
    when = row.occurred_at or _now()
    window = timedelta(minutes=settings.POS_MATCH_WINDOW_MINUTES)

    # 1) Expected payment: amount matches, terminal matches when both are known.
    exp_stmt = select(ExpectedPosPayment).where(
        ExpectedPosPayment.status == "PENDING",
        ExpectedPosPayment.amount >= amt - _EPS,
        ExpectedPosPayment.amount <= amt + _EPS,
    ).order_by(ExpectedPosPayment.created_at.asc())
    for exp in db.scalars(exp_stmt).all():
        if exp.terminal_id and row.terminal_id and exp.terminal_id != row.terminal_id:
            continue
        inv = db.get(Invoice, exp.invoice_id)
        if inv is None or inv.voided_at is not None:
            continue
        res = _record_payment_for(db, exp.invoice_id, amt,
                                  user_id=exp.created_by_user_id, reference=row.reference)
        if res.get("status") != "OK":
            continue  # e.g. amount exceeds balance — leave for manual review
        exp.status = "MATCHED"
        exp.pos_transaction_id = row.id
        _mark_matched(row, exp.invoice_id, res["payment_id"], "AUTO_EXPECTED",
                      expected_id=exp.id)
        db.commit()
        return

    # 2) Exactly one open invoice whose balance equals the amount, within the window.
    since = when - window
    candidates = [
        inv for inv in db.scalars(
            select(Invoice).where(
                Invoice.voided_at.is_(None),
                Invoice.payment_status != "PAID",
                Invoice.created_at >= since,
            )
        ).all()
        if abs(receivables.balance(inv) - amt) <= _EPS
    ]
    if len(candidates) == 1:
        inv = candidates[0]
        res = _record_payment_for(db, inv.id, amt, user_id=None, reference=row.reference)
        if res.get("status") == "OK":
            _mark_matched(row, inv.id, res["payment_id"], "AUTO_BALANCE")
            db.commit()
            return

    # Otherwise leave UNMATCHED for the reconcile screen.


def _mark_matched(row: PosTransaction, invoice_id: int, payment_id: int, method: str,
                  expected_id: int | None = None, user_id: int | None = None) -> None:
    row.status = "MATCHED"
    row.invoice_id = invoice_id
    row.payment_id = payment_id
    row.match_method = method
    row.expected_payment_id = expected_id
    row.matched_by_user_id = user_id
    row.matched_at = _now()


def assign_transaction(db: Session, *, txn_id: int, invoice_id: int,
                       user_id: int | None) -> dict:
    """Manually link an unmatched transaction to an invoice (records the payment)."""
    row = db.get(PosTransaction, txn_id)
    if row is None:
        return {"status": "NOT_FOUND"}
    if row.status == "MATCHED":
        return {"status": "ERROR", "error": "transaction is already matched"}
    inv = db.get(Invoice, invoice_id)
    if inv is None or inv.voided_at is not None:
        return {"status": "ERROR", "error": "invoice not found or voided"}
    res = _record_payment_for(db, invoice_id, float(row.amount), user_id=user_id,
                              reference=row.reference)
    if res.get("status") != "OK":
        return res
    _mark_matched(row, invoice_id, res["payment_id"], "MANUAL", user_id=user_id)
    db.commit()
    return {"status": "OK", "payment_id": res["payment_id"], "invoice_id": invoice_id}


def ignore_transaction(db: Session, *, txn_id: int, user_id: int | None) -> dict:
    row = db.get(PosTransaction, txn_id)
    if row is None:
        return {"status": "NOT_FOUND"}
    if row.status == "MATCHED":
        return {"status": "ERROR", "error": "cannot ignore a matched transaction"}
    row.status = "IGNORED"
    row.matched_by_user_id = user_id
    db.commit()
    return {"status": "OK"}


# --------------------------------------------------------------------------- #
# Suggestions — transparent feature-based ranking (the ML on-ramp).
# --------------------------------------------------------------------------- #
def suggestion_features(txn: PosTransaction, inv: Invoice, now: datetime) -> dict:
    """The features behind a suggestion's score — also the training signal for a
    learned ranker: each manual assignment pairs these features with the chosen
    invoice (label=1) vs the others shown (label=0)."""
    bal = receivables.balance(inv)
    amt = float(txn.amount or 0)
    amount_delta = abs(bal - amt)
    exact = amount_delta <= _EPS
    partial_fit = amt < bal - _EPS  # a plausible part-payment
    inv_when = inv.created_at or now
    if inv_when.tzinfo is None:
        inv_when = inv_when.replace(tzinfo=timezone.utc)
    txn_when = txn.occurred_at or now
    if txn_when.tzinfo is None:
        txn_when = txn_when.replace(tzinfo=timezone.utc)
    minutes_apart = abs((txn_when - inv_when).total_seconds()) / 60.0
    return {
        "exact_balance": exact,
        "partial_fit": partial_fit,
        "amount_delta": round(amount_delta, 2),
        "minutes_apart": round(minutes_apart, 1),
        "balance": round(bal, 2),
    }


def _score(f: dict) -> float:
    score = 0.0
    if f["exact_balance"]:
        score += 0.6
    elif f["partial_fit"]:
        score += 0.25
    # Closer in time is better (full credit within ~30 min, decaying after).
    score += max(0.0, 0.3 * (1 - min(f["minutes_apart"], 120) / 120))
    # Small residual amount difference still counts a little when not exact.
    if not f["exact_balance"] and f["amount_delta"] < 50:
        score += 0.1
    return round(min(score, 1.0), 3)


def suggest_invoices(db: Session, row: PosTransaction, limit: int = 3) -> list[dict]:
    now = _now()
    window = timedelta(minutes=max(settings.POS_MATCH_WINDOW_MINUTES * 6, 180))
    when = row.occurred_at or now
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    opens = db.scalars(
        select(Invoice).where(
            Invoice.voided_at.is_(None),
            Invoice.payment_status != "PAID",
            Invoice.created_at >= when - window,
        )
    ).all()
    cust_names = dict(db.execute(select(Customer.id, Customer.name)).all())
    scored = []
    for inv in opens:
        bal = receivables.balance(inv)
        if bal <= _EPS or float(row.amount) > bal + _EPS:
            continue  # can't pay more than is owed
        f = suggestion_features(row, inv, now)
        s = _score(f)
        if s <= 0:
            continue
        scored.append({
            "invoice_id": inv.id, "invoice_number": inv.invoice_number,
            "customer_name": cust_names.get(inv.customer_id) or "Walk-in",
            "balance": round(bal, 2), "score": s, "features": f,
        })
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:limit]


def list_unmatched(db: Session, *, limit: int = 50) -> list[dict]:
    rows = db.scalars(
        select(PosTransaction).where(PosTransaction.status == "UNMATCHED")
        .order_by(PosTransaction.received_at.desc()).limit(limit)
    ).all()
    return [{
        "id": r.id, "provider": r.provider, "amount": float(r.amount),
        "terminal_id": r.terminal_id, "reference": r.reference,
        "masked_pan": r.masked_pan,
        "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
        "received_at": r.received_at.isoformat() if r.received_at else None,
        "suggestions": suggest_invoices(db, r),
    } for r in rows]
