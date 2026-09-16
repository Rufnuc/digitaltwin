"""Tax API — VAT and income-tax estimate for a period (Nigeria defaults)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_role
from app.core.enums import Role
from app.models.user import User
from app.services import tax

router = APIRouter(tags=["tax"], prefix="/tax")


@router.get("/summary")
def summary(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.MANAGER)),
    start: date | None = Query(None),
    end: date | None = Query(None),
    include_demo: bool = Query(False),
) -> dict:
    """VAT + income-tax estimate for the period (default: trailing 12 months)."""
    return tax.tax_summary(db, start=start, end=end, include_demo=include_demo)
