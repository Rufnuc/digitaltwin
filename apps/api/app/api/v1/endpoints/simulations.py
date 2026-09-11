from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, Role, SimulationStatus
from app.models.simulation import SimulationRun
from app.models.user import User
from app.schemas.simulation import (
    CompareRequest,
    MonteCarloCreate,
    SensitivityRequest,
    SimulationCreate,
    SimulationOut,
)
from app.services import audit
from app.services.analytics import baseline_economics
from app.services.simulation.base import registered_scenario_types
from app.services.simulation.compare import compare_scenarios
from app.services.simulation.runner import run_monte_carlo_simulation, run_simulation
from app.services.simulation.sensitivity import default_variations, tornado

router = APIRouter(tags=["simulations"])


@router.get("/simulations/scenario-types")
def scenario_types(_: User = Depends(get_current_user)) -> dict:
    """Scenario types with a registered (implemented) engine, plus advanced modes."""
    return {
        "implemented": registered_scenario_types(),
        "advanced": ["monte_carlo", "sensitivity", "compare"],
    }


@router.post("/simulations/monte-carlo", response_model=SimulationOut,
             status_code=status.HTTP_201_CREATED)
def monte_carlo(
    payload: MonteCarloCreate,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.ANALYST)),
) -> SimulationRun:
    run = SimulationRun(
        name=payload.name,
        scenario_type=payload.scenario_type,
        parameters=payload.parameters,
        assumptions={},
        horizon_months=payload.horizon_months,
        iterations=payload.iterations,
        status=SimulationStatus.PENDING.value,
        created_by_id=user.id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run = run_monte_carlo_simulation(
        db, run, target_metric=payload.target_metric, target_threshold=payload.target_threshold
    )
    audit.record(
        db,
        action=AuditAction.RUN_SIMULATION,
        user_id=user.id,
        entity_type="simulation_run",
        entity_id=run.id,
        summary=f"monte_carlo {run.iterations} iterations",
    )
    return run


@router.post("/simulations/sensitivity")
def sensitivity(
    payload: SensitivityRequest,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ANALYST)),
) -> dict:
    baseline = baseline_economics(db)
    variations = payload.variations or default_variations()
    return tornado(baseline, payload.parameters, payload.assumptions, variations,
                   payload.target_metric)


@router.post("/simulations/compare")
def compare(
    payload: CompareRequest,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ANALYST)),
) -> dict:
    baseline = baseline_economics(db)
    return compare_scenarios(baseline, [s.model_dump() for s in payload.scenarios])


@router.get("/simulations")
def list_simulations(
    db: Session = Depends(db_session),
    _: User = Depends(get_current_user),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    stmt = select(SimulationRun).options(selectinload(SimulationRun.results))
    total = db.scalar(select(func.count()).select_from(SimulationRun.__table__))
    rows = db.scalars(stmt.order_by(SimulationRun.id.desc()).limit(limit).offset(offset)).all()
    return {
        "items": [SimulationOut.model_validate(r).model_dump(mode="json") for r in rows],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
    }


@router.get("/simulations/{run_id}", response_model=SimulationOut)
def get_simulation(
    run_id: int, db: Session = Depends(db_session), _: User = Depends(get_current_user)
) -> SimulationRun:
    obj = db.get(SimulationRun, run_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Simulation {run_id} not found")
    return obj


@router.post("/simulations", response_model=SimulationOut, status_code=status.HTTP_201_CREATED)
def create_simulation(
    payload: SimulationCreate,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.ANALYST)),
) -> SimulationRun:
    run = SimulationRun(
        name=payload.name,
        scenario_type=payload.scenario_type,
        parameters=payload.parameters,
        assumptions=payload.assumptions,
        horizon_months=payload.horizon_months,
        iterations=payload.iterations,
        status=SimulationStatus.PENDING.value,
        created_by_id=user.id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.post("/simulations/{run_id}/run", response_model=SimulationOut)
def run(
    run_id: int,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.ANALYST)),
) -> SimulationRun:
    obj = db.get(SimulationRun, run_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Simulation {run_id} not found")
    obj = run_simulation(db, obj)
    audit.record(
        db,
        action=AuditAction.RUN_SIMULATION,
        user_id=user.id,
        entity_type="simulation_run",
        entity_id=obj.id,
        summary=f"{obj.scenario_type} -> {obj.status}",
    )
    return obj
