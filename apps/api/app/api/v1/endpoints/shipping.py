from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models.user import User
from app.services.shipping import collector

router = APIRouter(tags=["shipping"])


@router.get("/shipping/status")
def status(_: User = Depends(get_current_user)) -> dict:
    """Live connection status and vessel counts for the AIS shipping monitor."""
    return collector.store.status()


@router.get("/shipping/vessels")
def vessels(
    _: User = Depends(get_current_user),
    region: str | None = Query(None, description="filter by region label"),
    nigeria_bound: bool | None = Query(None, description="only vessels bound for Nigeria"),
    limit: int = Query(200, le=1000),
) -> dict:
    """Latest known position per tracked vessel (real AIS observations)."""
    return {
        "items": collector.store.snapshot(region=region, nigeria_bound=nigeria_bound, limit=limit),
        "provenance": "REAL",
        "note": "Positions are real AIS observations. 'Bound for Nigeria' is derived from each "
                "vessel's self-reported destination — an intent signal, not a guarantee.",
    }
