from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user
from app.models.invoice import Invoice, InvoiceLine
from app.models.system import Alert
from app.models.user import User
from app.services.analytics import dashboard_summary

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary")
def summary(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    return dashboard_summary(db)


@router.get("/dashboard/revenue-timeseries")
def revenue_timeseries(
    db: Session = Depends(db_session), _: User = Depends(get_current_user)
) -> dict:
    """Monthly revenue from invoice lines. All values are computed, not invented.

    Aggregated in Python for cross-DB portability at Phase-1 data volumes;
    Phase 2 pushes this into a SQL/materialised aggregation for scale (spec §44).
    """
    rows = db.execute(
        select(Invoice.invoice_date, InvoiceLine.line_total).join(
            InvoiceLine, InvoiceLine.invoice_id == Invoice.id
        )
    ).all()
    agg: dict[str, float] = {}
    for d, amt in rows:
        key = d.strftime("%Y-%m")
        agg[key] = agg.get(key, 0.0) + float(amt or 0)
    points = [{"period": k, "revenue": round(v, 2)} for k, v in sorted(agg.items())]
    return {"series": points, "provenance": "MODEL_OUTPUT"}


@router.get("/dashboard/alerts")
def alerts(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    rows = db.scalars(
        select(Alert).where(Alert.is_resolved == False).order_by(Alert.created_at.desc())  # noqa: E712
    ).all()
    return {
        "items": [
            {
                "id": a.id,
                "severity": a.severity,
                "category": a.category,
                "title": a.title,
                "body": a.body,
                "data_origin": a.data_origin,
            }
            for a in rows
        ]
    }
