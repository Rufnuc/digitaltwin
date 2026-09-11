from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, Role
from app.models.user import User
from app.services import audit
from app.services.agents import simulation

router = APIRouter(tags=["agents"])

_NO_DATA = "No customer sales history to calibrate agents. Seed or import data first."


class SimulateRequest(BaseModel):
    policy: dict = Field(default_factory=dict)   # {price_change_percent, monthly_opex_delta}
    horizon_months: int = 12
    iterations: int = 400
    assumptions: dict = Field(default_factory=dict)
    seed: int = 42


class Strategy(BaseModel):
    name: str
    price_change_percent: float = 0.0
    monthly_opex_delta: float = 0.0


class CompareRequest(BaseModel):
    strategies: list[Strategy]
    horizon_months: int = 12
    iterations: int = 400
    assumptions: dict = Field(default_factory=dict)


@router.get("/agents/roster")
def roster(_: User = Depends(get_current_user)) -> dict:
    return {
        "agents": simulation.AGENT_ROSTER,
        "default_assumptions": simulation.DEFAULT_ASSUMPTIONS,
    }


@router.post("/agents/simulate")
def simulate(
    payload: SimulateRequest,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.ANALYST)),
) -> dict:
    result = simulation.simulate(
        db, payload.policy, payload.horizon_months, payload.iterations,
        payload.assumptions, payload.seed,
    )
    if result is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _NO_DATA)
    audit.record(
        db, action=AuditAction.RUN_SIMULATION, user_id=user.id, entity_type="agent_simulation",
        summary=f"multi-agent sim: {result['iterations']} iters × {result['horizon_months']}mo",
    )
    return result


@router.post("/agents/compare")
def compare(
    payload: CompareRequest,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ANALYST)),
) -> dict:
    result = simulation.compare_policies(
        db, [s.model_dump() for s in payload.strategies],
        payload.horizon_months, payload.iterations, payload.assumptions,
    )
    if result is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _NO_DATA)
    return result
