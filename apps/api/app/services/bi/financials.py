"""Financial analytics — monthly P&L time series (spec §16)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.expense import Expense
from app.models.invoice import Invoice, InvoiceLine
from app.services.analytics import pnl


def monthly_pnl(db: Session) -> dict:
    """Revenue, COGS, gross profit, opex and net profit per calendar month.

    Aggregated in Python for cross-DB portability at Phase-2 data volumes;
    Phase-2+ can push this to SQL/materialised views for scale (spec §44).
    """
    rev: dict[str, float] = {}
    cogs: dict[str, float] = {}
    for d, lt, qty, uc in db.execute(
        select(
            Invoice.invoice_date,
            InvoiceLine.line_total,
            InvoiceLine.quantity,
            InvoiceLine.unit_cost,
        ).join(InvoiceLine, InvoiceLine.invoice_id == Invoice.id)
    ).all():
        key = d.strftime("%Y-%m")
        rev[key] = rev.get(key, 0.0) + float(lt or 0)
        cogs[key] = cogs.get(key, 0.0) + float(qty or 0) * float(uc or 0)

    opex: dict[str, float] = {}
    for d, amt in db.execute(select(Expense.expense_date, Expense.amount)).all():
        key = d.strftime("%Y-%m")
        opex[key] = opex.get(key, 0.0) + float(amt or 0)

    periods = sorted(set(rev) | set(cogs) | set(opex))
    series = []
    for p in periods:
        row = pnl(rev.get(p, 0.0), cogs.get(p, 0.0), opex.get(p, 0.0))
        series.append(
            {
                "period": p,
                "revenue": round(row.revenue, 2),
                "cogs": round(row.cogs, 2),
                "gross_profit": round(row.gross_profit, 2),
                "operating_expenses": round(row.operating_expenses, 2),
                "net_profit": round(row.net_profit, 2),
                "gross_margin": round(row.gross_margin, 4),
                "net_margin": round(row.net_margin, 4),
            }
        )
    return {"series": series, "provenance": "MODEL_OUTPUT"}
