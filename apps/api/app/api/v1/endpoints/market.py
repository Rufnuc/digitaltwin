from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, Role
from app.models.user import User
from app.services import audit
from app.services.market_intelligence import ingest

router = APIRouter(tags=["market"])


@router.post("/market/refresh")
def refresh(
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.ANALYST)),
) -> dict:
    """Fetch real external economic data + news and store it with provenance."""
    try:
        result = ingest.refresh_market_data(db)
    except NotImplementedError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    except Exception as e:  # noqa: BLE001 — never let a source failure hang/500 the request
        import logging

        logging.getLogger("digitaltwin.market").warning("market refresh failed: %s", e)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Could not reach the market-data sources right now. Please try again shortly.",
        ) from None
    audit.record(
        db, action=AuditAction.IMPORT, user_id=user.id, entity_type="market_data",
        summary=f"refresh: {result['indicators_ingested']} new indicators, "
                f"{result['news_ingested']} news",
    )
    return result


@router.get("/market/diagnostics")
def diagnostics(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.ANALYST)),
) -> dict:
    """Live connectivity test from the server to each market-data source, so an
    unreachable source (egress blocked, DNS, or the source blocking the server's IP)
    is obvious."""
    from app.services.market_intelligence.live import diagnose_sources

    return {"items": diagnose_sources(), "provider": "live"}


@router.get("/market/indicators")
def indicators(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    return {"items": ingest.latest_indicators(db)}


@router.get("/market/events")
def events(
    db: Session = Depends(db_session),
    _: User = Depends(get_current_user),
    min_relevance: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(20, le=100),
) -> dict:
    return {"items": ingest.recent_events(db, limit=limit, min_relevance=min_relevance)}


@router.get("/market/summary")
def summary(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    return ingest.market_summary(db)
