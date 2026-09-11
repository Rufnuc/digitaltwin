"""Audit logging helper (spec §36). Records important operations centrally."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.models.system import AuditLog


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
