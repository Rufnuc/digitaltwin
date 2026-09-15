"""Notifications: generate them from real business conditions, and read/mark them.

Notifications are broadcast (user_id NULL) in this single-business app. Generation
is idempotent — each category is de-duplicated within a time window so repeated
scans don't spam. Everything a notification reports is derived from real data or
model output; nothing is invented.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.extraction import ExtractedInvoice
from app.models.inventory import Inventory
from app.models.system import Alert, Notification
from app.services.bi.customers import customer_intelligence
from app.services.bi.data_quality import data_quality_report

_DEDUPE_HOURS = 6


def notify(
    db: Session, *, category: str, title: str, body: str | None = None,
    severity: str = "info", link: str | None = None, dedupe_hours: int = _DEDUPE_HOURS,
    supersede: bool = False, commit: bool = True,
) -> Notification | None:
    """Create a notification, avoiding pile-up of the same category.

    supersede=True (for standing-condition alerts like low stock or market impact):
    keep exactly ONE notification per category. The latest is updated in place and
    any older duplicates of that category are removed, so the same condition never
    stacks up across scans. It only re-alerts (resets is_read + created_at) when the
    message actually changes; an unchanged condition returns None (no new alert).

    supersede=False: legacy time-window dedupe — skip if one of the same category
    was created within `dedupe_hours`.
    """
    if supersede:
        rows = list(db.scalars(
            select(Notification)
            .where(Notification.category == category)
            .order_by(Notification.created_at.desc())
        ).all())
        keep = rows[0] if rows else None
        # Collapse any historical duplicates of this category down to one row.
        if len(rows) > 1:
            db.execute(
                delete(Notification).where(
                    Notification.category == category, Notification.id != keep.id
                )
            )
        if keep is not None:
            changed = (
                keep.title != title or keep.body != body
                or keep.severity != severity or keep.link != link
            )
            if changed:
                keep.title, keep.body = title, body
                keep.severity, keep.link = severity, link
                keep.is_read = False
                keep.created_at = datetime.now(timezone.utc)
            if commit:
                db.commit()
                db.refresh(keep)
            return keep if changed else None
        # No existing row — fall through and create one.
    elif dedupe_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=dedupe_hours)
        exists = db.scalar(
            select(Notification.id).where(
                Notification.category == category, Notification.created_at >= cutoff
            )
        )
        if exists:
            return None
    n = Notification(category=category, title=title, body=body, severity=severity, link=link)
    db.add(n)
    if commit:
        db.commit()
        db.refresh(n)
    return n


def generate(db: Session) -> dict:
    """Scan the business for notification-worthy conditions and create notifications."""
    created: list[str] = []

    def add(**kw) -> None:
        # Each condition below is a single standing aggregate — keep one live
        # notification per category (supersede) so scans never pile up duplicates.
        if notify(db, commit=False, supersede=True, **kw) is not None:
            created.append(kw["category"])

    # Low stock (quantity at or below safety stock).
    low = int(db.scalar(
        select(func.count()).select_from(Inventory).where(
            Inventory.safety_stock.is_not(None),
            Inventory.quantity_on_hand <= Inventory.safety_stock,
        )
    ) or 0)
    if low:
        add(category="low_stock", severity="high",
            title=f"{low} product{'s' if low != 1 else ''} low on stock",
            body="Stock is at or below safety level — consider reordering.", link="/inventory")

    # Quant reorder brain: deterministic order-up-to recommendations across the
    # catalogue. This is the smarter signal than the static safety-stock check —
    # it says HOW MUCH to order and the capital needed. Guarded so a quant error
    # never blocks the rest of notification generation.
    try:
        from app.services.quant import enabled as quant_enabled
        from app.services.quant import service as qsvc

        if quant_enabled():
            scan = qsvc.reorder_scan(db)
            n_order = scan["counts"]["to_order_now"]
            if n_order:
                cost = scan["total_estimated_restock_cost"]
                cost_txt = f" (about ₦{cost:,.0f} to restock)" if cost else ""
                add(category="reorder", severity="high",
                    title=f"{n_order} product{'s' if n_order != 1 else ''} to reorder now",
                    body=f"Forecast-based reorder recommendations are ready{cost_txt}.",
                    link="/suggestions")
    except Exception:  # noqa: BLE001 — never let the quant scan break notifications
        pass

    # Churn risk.
    try:
        ci = customer_intelligence(db)
        at_risk = ci["summary"]["at_risk_count"]
        if at_risk:
            add(category="churn", severity="medium",
                title=f"{at_risk} customer{'s' if at_risk != 1 else ''} at churn risk",
                body="Purchase activity has fallen well below their usual cadence.",
                link="/analytics")
    except Exception:  # noqa: BLE001 — never let one check break generation
        pass

    # Data quality.
    dq = data_quality_report(db)
    if dq["issues"]:
        n_issues = len(dq["issues"])
        add(category="data_quality", severity="medium",
            title=f"Data quality: {n_issues} issue categor{'y' if n_issues == 1 else 'ies'}",
            body=f"Quality score {dq['score']} (grade {dq['grade']}).", link="/data-quality")

    # Open market-impact alerts.
    impact_alerts = int(db.scalar(
        select(func.count()).select_from(Alert).where(
            Alert.category == "market_impact", Alert.is_resolved == False  # noqa: E712
        )
    ) or 0)
    if impact_alerts:
        add(category="market_impact", severity="high",
            title=f"{impact_alerts} market-impact alert{'s' if impact_alerts != 1 else ''}",
            body="Market signals could materially affect profit.", link="/impact")

    # Documents awaiting review.
    to_review = int(db.scalar(
        select(func.count()).select_from(ExtractedInvoice).where(
            ExtractedInvoice.status == "NEEDS_REVIEW"
        )
    ) or 0)
    if to_review:
        add(category="documents", severity="medium",
            title=f"{to_review} document{'s' if to_review != 1 else ''} awaiting review",
            body="Extracted invoices need verification before entering the books.",
            link="/documents")

    # Shipping bound for Nigeria (only if the monitor is active).
    try:
        from app.services.shipping import collector
        ng = collector.store.status().get("nigeria_bound", 0)
        if ng:
            add(category="shipping", severity="info",
                title=f"{ng} vessel{'s' if ng != 1 else ''} bound for Nigeria",
                body="Live AIS shows shipments heading to Nigerian ports.", link="/shipping")
    except Exception:  # noqa: BLE001
        pass

    db.commit()
    return {"created": len(created), "categories": created}


# --------------------------------------------------------------------------- #
# Reads.
# --------------------------------------------------------------------------- #
def _to_dict(n: Notification) -> dict:
    return {
        "id": n.id, "title": n.title, "body": n.body, "category": n.category,
        "severity": n.severity, "link": n.link, "is_read": n.is_read,
        "created_at": n.created_at.isoformat(),
    }


def list_notifications(db: Session, unread_only: bool = False, limit: int = 50) -> list[dict]:
    stmt = select(Notification).order_by(Notification.created_at.desc()).limit(limit)
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)  # noqa: E712
    return [_to_dict(n) for n in db.scalars(stmt).all()]


def unread_count(db: Session) -> int:
    return int(db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.is_read == False  # noqa: E712
        )
    ) or 0)


def mark_read(db: Session, notification_id: int) -> bool:
    n = db.get(Notification, notification_id)
    if n is None:
        return False
    n.is_read = True
    db.commit()
    return True


def mark_all_read(db: Session) -> int:
    from sqlalchemy import update
    res = db.execute(
        update(Notification).where(Notification.is_read == False).values(is_read=True)  # noqa: E712
    )
    db.commit()
    return res.rowcount or 0
