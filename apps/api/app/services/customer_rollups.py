"""Keep the materialised customer rollups (lifetime revenue, order count, first/last
purchase) in step with their invoices. Called after a sale and as a backfill."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.invoice import Invoice


def recompute_one(db: Session, customer_id: int, commit: bool = True) -> None:
    cust = db.get(Customer, customer_id)
    if cust is None:
        return
    total, cnt, first, last = db.execute(
        select(
            func.coalesce(func.sum(Invoice.total), 0),
            func.count(Invoice.id),
            func.min(Invoice.invoice_date),
            func.max(Invoice.invoice_date),
        ).where(Invoice.customer_id == customer_id, Invoice.voided_at.is_(None))
    ).one()
    cust.lifetime_revenue = round(float(total or 0), 2)
    cust.order_count = int(cnt or 0)
    cust.first_purchase_date = first
    cust.last_purchase_date = last
    if commit:
        db.commit()


def recompute_all(db: Session) -> int:
    """Backfill every customer's rollups. Returns how many were updated."""
    ids = list(db.scalars(select(Customer.id)).all())
    for cid in ids:
        recompute_one(db, cid, commit=False)
    db.commit()
    return len(ids)
