"""Per-customer analytics: how much they buy, how often, whether they come back,
and what they buy — computed from real invoices (never invented)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceLine
from app.models.product import Product


def _months_back(n: int) -> list[str]:
    """The last n year-month keys ('YYYY-MM'), oldest first, ending this month."""
    today = date.today()
    y, m = today.year, today.month
    keys: list[str] = []
    for _ in range(n):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(keys))


def customer_analytics(db: Session, customer_id: int, months: int = 12) -> dict | None:
    cust = db.get(Customer, customer_id)
    if cust is None or getattr(cust, "deleted_at", None) is not None:
        return None

    invs = db.scalars(
        select(Invoice).where(Invoice.customer_id == customer_id)
        .order_by(Invoice.invoice_date)
    ).all()

    orders = len(invs)
    revenue = round(sum(float(i.total or 0) for i in invs), 2)
    dates = [i.invoice_date for i in invs if i.invoice_date]
    first_order = min(dates).isoformat() if dates else None
    last_order = max(dates).isoformat() if dates else None
    avg_order_value = round(revenue / orders, 2) if orders else 0.0
    days_since_last = (date.today() - max(dates)).days if dates else None
    # Average days between consecutive orders (purchase cadence).
    sorted_dates = sorted(dates)
    gaps = [(sorted_dates[i] - sorted_dates[i - 1]).days for i in range(1, len(sorted_dates))]
    avg_days_between = round(sum(gaps) / len(gaps), 1) if gaps else None
    orders_last_90d = sum(1 for d in dates if (date.today() - d).days <= 90)

    # Monthly revenue + order count, last `months` months (zero-filled for the chart).
    keys = _months_back(months)
    rev_by_month = {k: 0.0 for k in keys}
    ord_by_month = {k: 0 for k in keys}
    for i in invs:
        if not i.invoice_date:
            continue
        k = i.invoice_date.strftime("%Y-%m")
        if k in rev_by_month:
            rev_by_month[k] += float(i.total or 0)
            ord_by_month[k] += 1
    monthly = [{"month": k, "revenue": round(rev_by_month[k], 2), "orders": ord_by_month[k]}
               for k in keys]

    # Top products this customer buys (by revenue).
    inv_ids = [i.id for i in invs]
    top_products: list[dict] = []
    if inv_ids:
        rows = db.execute(
            select(InvoiceLine.product_id, Product.code, Product.name,
                   func.coalesce(func.sum(InvoiceLine.quantity), 0),
                   func.coalesce(func.sum(InvoiceLine.line_total), 0))
            .join(Product, Product.id == InvoiceLine.product_id, isouter=True)
            .where(InvoiceLine.invoice_id.in_(inv_ids))
            .group_by(InvoiceLine.product_id, Product.code, Product.name)
            .order_by(func.sum(InvoiceLine.line_total).desc())
            .limit(5)
        ).all()
        top_products = [{"product_id": pid, "code": code, "name": name,
                         "quantity": float(q or 0), "revenue": round(float(v or 0), 2)}
                        for pid, code, name, q, v in rows]

    return {
        "customer_id": cust.id, "customer_name": cust.name,
        "orders": orders, "revenue": revenue, "avg_order_value": avg_order_value,
        "first_order": first_order, "last_order": last_order,
        "days_since_last": days_since_last, "avg_days_between_orders": avg_days_between,
        "orders_last_90d": orders_last_90d,
        "returning": orders > 1,  # a repeat buyer, not a one-off
        "monthly": monthly, "top_products": top_products,
        "provenance": "REAL",
    }
