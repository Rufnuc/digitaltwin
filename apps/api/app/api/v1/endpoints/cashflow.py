"""Cash-flow API — money in vs out and outstanding balances."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_role
from app.core.enums import Role
from app.models.user import User
from app.services import cashflow

router = APIRouter(tags=["cashflow"], prefix="/cashflow")


@router.get("/summary")
def summary(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.MANAGER)),
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Money in/out over the trailing window, net, and owed-to-us vs we-owe."""
    return cashflow.cash_flow_summary(db, days=days)
