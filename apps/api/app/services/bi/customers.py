"""Customer intelligence (spec §24).

Every figure is computed from stored invoice lines. Churn is only *flagged as
risk* from evidence (recency vs. the customer's own cadence) — never asserted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceLine


@dataclass
class CustomerMetrics:
    customer_id: int
    code: str
    name: str
    revenue: float
    gross_profit: float
    gross_margin: float
    orders: int
    units: float
    avg_order_value: float
    first_purchase: str | None
    last_purchase: str | None
    recency_days: int | None
    avg_interval_days: float | None
    churn_risk: bool
    churn_reason: str | None


def _row_metrics(row, today: date) -> CustomerMetrics:
    (
        cid, code, name, revenue, cogs, orders, units, first_d, last_d,
    ) = row
    revenue = float(revenue or 0)
    cogs = float(cogs or 0)
    orders = int(orders or 0)
    gross_profit = revenue - cogs
    gross_margin = gross_profit / revenue if revenue else 0.0
    aov = revenue / orders if orders else 0.0

    recency = (today - last_d).days if last_d else None
    interval = None
    if first_d and last_d and orders > 1:
        span = (last_d - first_d).days
        interval = span / (orders - 1) if orders > 1 else None

    # Risk requires enough history AND a gap materially beyond the usual cadence.
    churn_risk = False
    reason = None
    if orders >= 3 and recency is not None and interval and interval > 0:
        if recency > 1.5 * interval:
            churn_risk = True
            reason = (
                f"{recency}d since last order vs ~{interval:.0f}d typical interval"
            )
    return CustomerMetrics(
        customer_id=cid, code=code, name=name, revenue=round(revenue, 2),
        gross_profit=round(gross_profit, 2), gross_margin=round(gross_margin, 4),
        orders=orders, units=float(units or 0), avg_order_value=round(aov, 2),
        first_purchase=first_d.isoformat() if first_d else None,
        last_purchase=last_d.isoformat() if last_d else None,
        recency_days=recency,
        avg_interval_days=round(interval, 1) if interval else None,
        churn_risk=churn_risk, churn_reason=reason,
    )


def customer_metrics(db: Session) -> list[CustomerMetrics]:
    stmt = (
        select(
            Customer.id,
            Customer.code,
            Customer.name,
            func.coalesce(func.sum(InvoiceLine.line_total), 0),
            func.coalesce(func.sum(InvoiceLine.quantity * InvoiceLine.unit_cost), 0),
            func.count(func.distinct(Invoice.id)),
            func.coalesce(func.sum(InvoiceLine.quantity), 0),
            func.min(Invoice.invoice_date),
            func.max(Invoice.invoice_date),
        )
        .select_from(Customer)
        .join(Invoice, Invoice.customer_id == Customer.id, isouter=True)
        .join(InvoiceLine, InvoiceLine.invoice_id == Invoice.id, isouter=True)
        .group_by(Customer.id, Customer.code, Customer.name)
    )
    today = date.today()
    return [_row_metrics(r, today) for r in db.execute(stmt).all()]


def customer_intelligence(db: Session, top_n: int = 10) -> dict:
    metrics = customer_metrics(db)
    with_sales = [m for m in metrics if m.orders > 0]
    total_revenue = sum(m.revenue for m in with_sales) or 0.0

    by_profit = sorted(with_sales, key=lambda m: m.gross_profit, reverse=True)
    at_risk = [m for m in with_sales if m.churn_risk]

    # Concentration risk: revenue share of the top customer / top 5 (spec §24).
    top1_share = (by_profit[0].revenue / total_revenue) if total_revenue and by_profit else 0.0
    top5_share = (
        sum(m.revenue for m in sorted(with_sales, key=lambda m: m.revenue, reverse=True)[:5])
        / total_revenue
        if total_revenue
        else 0.0
    )

    return {
        "summary": {
            "customers_with_sales": len(with_sales),
            "total_revenue": round(total_revenue, 2),
            "at_risk_count": len(at_risk),
            "top1_revenue_share": round(top1_share, 4),
            "top5_revenue_share": round(top5_share, 4),
        },
        "top_by_profit": [m.__dict__ for m in by_profit[:top_n]],
        "at_risk": [m.__dict__ for m in at_risk[:top_n]],
        "provenance": "MODEL_OUTPUT",
    }
