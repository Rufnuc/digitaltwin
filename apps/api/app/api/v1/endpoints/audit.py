"""Audit trail / activity log API — read the automatic traceability record."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_role
from app.core.enums import Role
from app.models.user import User
from app.services import audit

router = APIRouter(tags=["audit"])


@router.get("/audit")
def list_activity(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ANALYST)),
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    user_id: int | None = Query(None),
    action: str | None = Query(None),
    source: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """The activity log: every recorded create/update/delete, newest first, filterable."""
    return audit.list_audit(
        db, entity_type=entity_type, entity_id=entity_id, user_id=user_id,
        action=action, source=source, since=since, until=until,
        limit=limit, offset=offset,
    )


@router.get("/audit/entity/{entity_type}/{entity_id}")
def record_history(
    entity_type: str,
    entity_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ANALYST)),
) -> dict:
    """The full change history (timeline) of one record."""
    return audit.entity_history(db, entity_type, entity_id)
