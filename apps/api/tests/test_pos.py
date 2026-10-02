"""POS reconciliation: expectations, auto-match (full + partial), manual assign,
suggestions."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.services import receivables
from app.services.pos import reconcile
from app.services.pos.base import PosTxn


@pytest.fixture
def invoice(db):
    c = Customer(code="CUS-POS", name="POS Customer")
    db.add(c)
    db.commit()
    inv = Invoice(invoice_number="INV-POS-1", invoice_date=date(2026, 3, 1),
                  customer_id=c.id, subtotal=5000, total=5000, payment_status="UNPAID",
                  version_no=1)
    db.add(inv)
    db.commit()
    return inv


def _txn(txn_id: str, amount: float, terminal: str | None = None) -> PosTxn:
    return PosTxn(provider="moniepoint", provider_txn_id=txn_id, amount=amount,
                  terminal_id=terminal, reference=f"RRN{txn_id}",
                  occurred_at=datetime.now(timezone.utc))


def test_expected_payment_auto_matches_full(db, invoice):
    reconcile.create_expected(db, invoice_id=invoice.id, amount=5000,
                              terminal_id="T1", user_id=1)
    row = reconcile.ingest_transaction(db, _txn("TX1", 5000, terminal="T1"))
    db.refresh(row)
    assert row.status == "MATCHED"
    assert row.match_method == "AUTO_EXPECTED"
    db.refresh(invoice)
    assert invoice.payment_status == "PAID"
    assert receivables.balance(invoice) == 0


def test_expected_payment_auto_matches_partial(db, invoice):
    # Customer pays only 2000 of 5000 on the POS.
    reconcile.create_expected(db, invoice_id=invoice.id, amount=2000,
                              terminal_id="T1", user_id=1)
    row = reconcile.ingest_transaction(db, _txn("TX2", 2000, terminal="T1"))
    db.refresh(row)
    assert row.status == "MATCHED"
    db.refresh(invoice)
    assert invoice.payment_status == "PARTIAL"
    assert receivables.balance(invoice) == 3000


def test_webhook_is_idempotent(db, invoice):
    reconcile.create_expected(db, invoice_id=invoice.id, amount=5000, terminal_id=None, user_id=1)
    r1 = reconcile.ingest_transaction(db, _txn("DUP", 5000))
    r2 = reconcile.ingest_transaction(db, _txn("DUP", 5000))  # retransmit
    assert r1.id == r2.id
    db.refresh(invoice)
    # Paid exactly once, not twice.
    assert float(invoice.amount_paid) == 5000


def test_exact_balance_auto_match_without_expectation(db, invoice):
    row = reconcile.ingest_transaction(db, _txn("TX3", 5000))
    db.refresh(row)
    assert row.status == "MATCHED"
    assert row.match_method == "AUTO_BALANCE"


def test_ambiguous_amount_stays_unmatched_with_suggestions(db, invoice):
    # A second open invoice with the same balance makes the amount ambiguous.
    inv2 = Invoice(invoice_number="INV-POS-2", invoice_date=date(2026, 3, 1),
                   customer_id=invoice.customer_id, subtotal=5000, total=5000,
                   payment_status="UNPAID", version_no=1)
    db.add(inv2)
    db.commit()
    row = reconcile.ingest_transaction(db, _txn("TX4", 5000))
    db.refresh(row)
    assert row.status == "UNMATCHED"
    unmatched = reconcile.list_unmatched(db)
    assert unmatched and unmatched[0]["id"] == row.id
    # Both invoices are suggested.
    sugg_ids = {s["invoice_id"] for s in unmatched[0]["suggestions"]}
    assert {invoice.id, inv2.id} <= sugg_ids


def test_manual_assign_records_payment(db, invoice):
    inv2 = Invoice(invoice_number="INV-POS-3", invoice_date=date(2026, 3, 1),
                   customer_id=invoice.customer_id, subtotal=5000, total=5000,
                   payment_status="UNPAID", version_no=1)
    db.add(inv2)
    db.commit()
    row = reconcile.ingest_transaction(db, _txn("TX5", 5000))  # ambiguous → unmatched
    assert row.status == "UNMATCHED"
    res = reconcile.assign_transaction(db, txn_id=row.id, invoice_id=invoice.id, user_id=1)
    assert res["status"] == "OK"
    db.refresh(invoice)
    assert invoice.payment_status == "PAID"
    db.refresh(row)
    assert row.status == "MATCHED"
    assert row.match_method == "MANUAL"
