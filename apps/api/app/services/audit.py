"""Audit logging helper (spec §36). Records important operations centrally, and
reads the automatic audit trail back for the activity log / traceability views."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.models.system import AuditLog
from app.models.user import User


def record(
    db: Session,
    *,
    action: AuditAction | str,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    summary: str | None = None,
    source: str = "api",
    commit: bool = True,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=action.value if isinstance(action, AuditAction) else action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        summary=summary,
        source=source,
    )
    db.add(log)
    if commit:
        db.commit()
        db.refresh(log)
    return log


# --------------------------------------------------------------------------- #
# Reads — the activity log / per-record history for traceability.
# --------------------------------------------------------------------------- #
def _to_dict(row: AuditLog, actor_name: str | None) -> dict:
    return {
        "id": row.id,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "user_id": row.user_id,
        "user_name": actor_name,
        "source": row.source,
        "summary": row.summary,
        "old_value": row.old_value,
        "new_value": row.new_value,
        "at": row.created_at.isoformat() if row.created_at else None,
    }


def list_audit(
    db: Session, *, entity_type: str | None = None, entity_id: int | None = None,
    user_id: int | None = None, action: str | None = None, source: str | None = None,
    since: datetime | None = None, until: datetime | None = None,
    limit: int = 50, offset: int = 0,
) -> dict:
    """Filtered, newest-first page of the audit trail, with actor names resolved."""
    conds = []
    if entity_type:
        conds.append(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        conds.append(AuditLog.entity_id == entity_id)
    if user_id is not None:
        conds.append(AuditLog.user_id == user_id)
    if action:
        conds.append(AuditLog.action == action)
    if source:
        conds.append(AuditLog.source == source)
    if since:
        conds.append(AuditLog.created_at >= since)
    if until:
        conds.append(AuditLog.created_at <= until)

    total = int(db.scalar(select(func.count()).select_from(AuditLog).where(*conds)) or 0)
    rows = db.scalars(
        select(AuditLog).where(*conds)
        .order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    ).all()
    names = _actor_names(db, {r.user_id for r in rows if r.user_id})
    return {
        "items": [_to_dict(r, names.get(r.user_id)) for r in rows],
        "total": total, "limit": limit, "offset": offset,
    }


def entity_history(db: Session, entity_type: str, entity_id: int, limit: int = 200) -> dict:
    """Full change history of one record, oldest first (a traceability timeline)."""
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.id).limit(limit)
    ).all()
    names = _actor_names(db, {r.user_id for r in rows if r.user_id})
    return {
        "entity_type": entity_type, "entity_id": entity_id,
        "events": [_to_dict(r, names.get(r.user_id)) for r in rows],
    }


def _actor_names(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(User.id, User.full_name, User.email).where(User.id.in_(user_ids))
    ).all()
    return {uid: (name or email) for uid, name, email in rows}
