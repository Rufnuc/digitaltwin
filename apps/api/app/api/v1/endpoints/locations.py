from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.config import settings
from app.core.enums import Role
from app.models.user import User
from app.services import locations

router = APIRouter(tags=["locations"], prefix="/locations")


class PingIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy: float | None = None


@router.post("/ping")
def ping(
    payload: PingIn,
    db: Session = Depends(db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Record the current user's location (sent by their browser while logged in)."""
    if not settings.GEO_TRACKING_ENABLED:
        return {"status": "DISABLED"}
    return locations.record_ping(db, user=user, lat=payload.lat, lng=payload.lng,
                                 accuracy=payload.accuracy)


@router.get("/latest")
def latest(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.MANAGER)),
) -> dict:
    """Latest position per user — the pins for the live map (managers and above)."""
    return {"items": locations.latest_per_user(db)}


@router.get("/users/{user_id}/history")
def user_history(
    user_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.MANAGER)),
    limit: int = Query(200, le=1000),
) -> dict:
    return {"items": locations.history(db, user_id=user_id, limit=limit)}
