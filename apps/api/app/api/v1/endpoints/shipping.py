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
    region: str | None = Query(None, description="filter by current region label"),
    origin: str | None = Query(None, description="filter by origin lane (e.g. 'China / Asia')"),
    nigeria_bound: bool | None = Query(None, description="only vessels declaring a Nigerian port"),
    nigeria_watch: bool | None = Query(
        None, description="vessels that will (declared) or did (observed) touch Nigeria"),
    limit: int = Query(200, le=1000),
) -> dict:
    """Latest known position per tracked vessel (real AIS observations)."""
    return {
        "items": collector.store.snapshot(
            region=region, origin=origin, nigeria_bound=nigeria_bound,
            nigeria_watch=nigeria_watch, limit=limit),
        "provenance": "REAL",
        "note": "Positions are real AIS observations. 'Bound for Nigeria' is the ship's own "
                "declared destination (intent, not a guarantee); 'arrived' means a China/Turkey-"
                "origin vessel we tracked has since been seen in Nigerian waters.",
    }


@router.get("/shipping/arrivals")
def arrivals(
    _: User = Depends(get_current_user),
    origin: str | None = Query(None, description="filter by origin lane (e.g. 'China / Asia')"),
    limit: int = Query(200, le=1000),
) -> dict:
    """Vessels tracked from China/Turkey that have since been observed in Nigerian
    waters — a confirmed arrival, not a self-reported intent."""
    items = [v for v in collector.store.snapshot(origin=origin, limit=1000)
             if v["arrived_nigeria"]]
    items.sort(key=lambda v: v["last_seen"] or "", reverse=True)
    return {
        "items": items[:limit],
        "count": len(items),
        "provenance": "REAL",
        "note": "Confirmed arrivals: a vessel we first tracked in a source lane (China or "
                "Turkey) has since reported a position inside Nigerian waters.",
    }
