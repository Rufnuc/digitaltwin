"""Bespoke customer reads (analytics). CRUD for customers is registered generically."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user
from app.models.user import User
from app.services import customer_analytics

router = APIRouter(tags=["customers"])


@router.get("/customers/{customer_id}/analytics")
def analytics(customer_id: int, _: User = Depends(get_current_user),
              db: Session = Depends(db_session)) -> dict:
    """Sales over time, order cadence, repeat/returning signal, and top products."""
    r = customer_analytics.customer_analytics(db, customer_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"customer {customer_id} not found")
    return r
