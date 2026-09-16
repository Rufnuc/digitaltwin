"""Traceability API — supplier detail (products/warehouses/shipments/payments)
and a product's suppliers."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import Role
from app.models.user import User
from app.services import supplier_trace

router = APIRouter(tags=["traceability"])


@router.get("/suppliers/{supplier_id}/trace")
def supplier_trace_endpoint(
    supplier_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    """A supplier's full picture: products supplied, warehouses, shipments, what we
    owe, and payments made."""
    r = supplier_trace.supplier_detail(db, supplier_id)
    if r.get("status") == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "supplier not found")
    return r


@router.get("/products/{product_id}/suppliers")
def product_suppliers(
    product_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(get_current_user),
) -> dict:
    """Which suppliers have supplied a product (from received stock)."""
    return {"items": supplier_trace.product_suppliers(db, product_id)}
