"""Quant inventory & decision-support API (spec v4 §11, Phase 1).

Read-only, deterministic endpoints for demand forecasting, reorder policy and ABC
classification. Gated by settings.QUANT_INVENTORY_ENABLED; every response carries
the config version for reproducibility.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import Role
from app.models.user import User
from app.services import quant
from app.services.quant import service as qsvc

router = APIRouter(tags=["quant"])


def _require_enabled() -> None:
    if not quant.enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "quant module is disabled")


@router.get("/quant/products/{product_id}/forecast")
def forecast(
    product_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(get_current_user),
    horizon_periods: int = Query(12, ge=1, le=730),
    seed: int = Query(42, ge=0),
    include_demo: bool = Query(False),
) -> dict:
    """Demand-pattern classification + a PredictiveDistribution forecast."""
    _require_enabled()
    result = qsvc.product_forecast(db, product_id, horizon=horizon_periods, seed=seed,
                                   include_demo=include_demo)
    if result["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {product_id} not found")
    return result


@router.get("/quant/products/{product_id}/reorder")
def reorder(
    product_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ANALYST)),
    service_level: float | None = Query(None, ge=0.5, le=0.999),
    review_period_days: int = Query(7, ge=1, le=365),
    include_demo: bool = Query(False),
) -> dict:
    """Periodic-review order-up-to recommendation with a forecast-quality gate.

    Omit service_level for the ABC-aware default (A items protected more)."""
    _require_enabled()
    result = qsvc.product_reorder(db, product_id, service_level=service_level,
                                  review_period_days=review_period_days,
                                  include_demo=include_demo)
    if result["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {product_id} not found")
    return result


@router.get("/quant/products/{product_id}/simulate")
def simulate(
    product_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ANALYST)),
    service_level: float | None = Query(None, ge=0.5, le=0.999),
    horizon_days: int = Query(90, ge=7, le=365),
    iterations: int = Query(2000, ge=100, le=10000),
    seed: int = Query(42, ge=0),
    mode: str = Query("lost_sales", pattern="^(lost_sales|backorder)$"),
    include_demo: bool = Query(False),
) -> dict:
    """Daily inventory-policy Monte Carlo: stockout probability, fill rate, cycle
    service level and expected lost units under the ABC-aware reorder policy."""
    _require_enabled()
    result = qsvc.product_simulation(
        db, product_id, service_level=service_level, horizon_days=horizon_days,
        iterations=iterations, seed=seed, mode=mode, include_demo=include_demo,
    )
    if result["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {product_id} not found")
    return result


@router.get("/quant/classification")
def classification(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ANALYST)),
    include_demo: bool = Query(False),
) -> dict:
    """ABC classification across the active catalogue (short-history products gated)."""
    _require_enabled()
    return qsvc.abc_report(db, include_demo=include_demo)
