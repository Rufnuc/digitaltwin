from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_role
from app.core.enums import AuditAction, Role
from app.models.user import User
from app.services import audit
from app.services.impact import engine

router = APIRouter(tags=["impact"])


class ScanRequest(BaseModel):
    assumptions: dict = Field(default_factory=dict)
    create_alerts: bool = True


@router.post("/impact/scan")
def scan(
    payload: ScanRequest,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.ANALYST)),
) -> dict:
    """Assess how current real market signals could affect the business (spec §31)."""
    result = engine.scan(db, payload.assumptions, create_alerts=payload.create_alerts)
    audit.record(
        db, action=AuditAction.RUN_SIMULATION, user_id=user.id, entity_type="market_impact",
        summary=f"impact scan: {len(result['assessments'])} assessments, "
                f"{result['alerts_created']} alerts",
    )
    return result


@router.get("/impact/drivers")
def drivers(_: User = Depends(require_role(Role.ANALYST))) -> dict:
    return {
        "drivers": list(engine.ASSESSORS.keys()),
        "default_assumptions": engine.DEFAULT_ASSUMPTIONS,
    }
