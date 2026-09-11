from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user
from app.core.enums import DataOrigin, Role, VerificationStatus
from app.models.system import AuditLog
from app.models.user import User

router = APIRouter(tags=["meta"])


@router.get("/meta/data-origins")
def data_origins(_: User = Depends(get_current_user)) -> dict:
    """The epistemic-status vocabulary the whole platform uses (spec §49)."""
    return {
        "data_origins": [e.value for e in DataOrigin],
        "verification_statuses": [e.value for e in VerificationStatus],
        "roles": [e.value for e in Role],
    }


@router.get("/audit-logs")
def audit_logs(
    db: Session = Depends(db_session),
    user: User = Depends(get_current_user),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "items": [
            {
                "id": a.id,
                "user_id": a.user_id,
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "summary": a.summary,
                "created_at": a.created_at.isoformat(),
            }
            for a in rows
        ]
    }
