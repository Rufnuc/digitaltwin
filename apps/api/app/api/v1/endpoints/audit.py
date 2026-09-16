"""Audit trail / activity log API — read the automatic traceability record."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
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


@router.get("/audit/export")
def export_activity(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ADMIN)),
    entity_type: str | None = Query(None),
    user_id: int | None = Query(None),
    action: str | None = Query(None),
    source: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
) -> Response:
    """Download the (filtered) activity log as CSV — admin only."""
    rows = audit.list_audit(
        db, entity_type=entity_type, user_id=user_id, action=action, source=source,
        since=since, until=until, limit=100000, offset=0,
    )["items"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "at", "action", "entity_type", "entity_id", "user", "source",
                "summary", "old_value", "new_value"])
    for e in rows:
        w.writerow([
            e["id"], e["at"], e["action"], e["entity_type"], e["entity_id"],
            e["user_name"] or "system", e["source"], e["summary"] or "",
            json.dumps(e["old_value"]) if e["old_value"] else "",
            json.dumps(e["new_value"]) if e["new_value"] else "",
        ])
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=activity-log-{stamp}.csv"},
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
