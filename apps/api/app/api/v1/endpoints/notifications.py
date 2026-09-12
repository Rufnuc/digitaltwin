from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user
from app.models.user import User
from app.services import notifications

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
def list_(
    db: Session = Depends(db_session),
    _: User = Depends(get_current_user),
    unread_only: bool = Query(False),
    limit: int = Query(50, le=200),
) -> dict:
    return {
        "items": notifications.list_notifications(db, unread_only=unread_only, limit=limit),
        "unread_count": notifications.unread_count(db),
    }


@router.get("/notifications/unread-count")
def unread(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    return {"unread_count": notifications.unread_count(db)}


@router.post("/notifications/generate")
def generate(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    """Refresh notifications from current business conditions (idempotent/deduped)."""
    return notifications.generate(db)


@router.post("/notifications/{notification_id}/read")
def read(
    notification_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(get_current_user),
) -> dict:
    if not notifications.mark_read(db, notification_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return {"ok": True}


@router.post("/notifications/read-all")
def read_all(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    return {"marked_read": notifications.mark_all_read(db)}
