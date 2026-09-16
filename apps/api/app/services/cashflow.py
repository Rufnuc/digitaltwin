"""Cash flow: money in vs money out, and what's expected next.

Combines the receivables and payables sides with expenses into the single view an
owner looks at daily: what came in and went out recently, the net, and what's owed
to us vs what we owe. All figures are REAL (recorded payments and expenses);
"expected" figures are outstanding balances, not forecasts.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.expense import Expense
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.purchase import Purchase, SupplierPayment


def _sum(db: Session, column, model, *conds) -> float:
    return float(db.scalar(
        select(func.coalesce(func.sum(column), 0)).select_from(model).where(*conds)
    ) or 0.0)


def cash_flow_summary(db: Session, days: int = 30, as_of: date | None = None) -> dict:
    """Money in/out over the trailing window, the net, and outstanding balances."""
    as_of = as_of or date.today()
    since = as_of - timedelta(days=days)

    money_in = _sum(db, Payment.amount, Payment,
                    Payment.status == "CONFIRMED", Payment.paid_at >= since,
                    Payment.paid_at <= as_of)
    supplier_out = _sum(db, SupplierPayment.amount, SupplierPayment,
                        SupplierPayment.status == "CONFIRMED",
                        SupplierPayment.paid_at >= since, SupplierPayment.paid_at <= as_of)
    expense_out = _sum(db, Expense.amount, Expense,
                       Expense.expense_date >= since, Expense.expense_date <= as_of)
    money_out = round(supplier_out + expense_out, 2)

    # Outstanding balances (what's owed both ways).
    receivable = _sum(db, Invoice.total - Invoice.amount_paid, Invoice,
                      Invoice.payment_status != "PAID")
    payable = _sum(db, Purchase.total - Purchase.amount_paid, Purchase,
                   Purchase.payment_status != "PAID")

    return {
        "as_of": as_of.isoformat(),
        "window_days": days,
        "money_in": round(money_in, 2),
        "money_out": money_out,
        "money_out_breakdown": {"supplier_payments": round(supplier_out, 2),
                                "expenses": round(expense_out, 2)},
        "net_cash_flow": round(money_in - money_out, 2),
        "owed_to_us": round(receivable, 2),          # receivables outstanding
        "we_owe": round(payable, 2),                 # payables outstanding
        "net_position": round(receivable - payable, 2),
        "provenance": "REAL",
        "note": "Recorded money in/out over the window; owed figures are current "
                "outstanding balances, not forecasts.",
    }
