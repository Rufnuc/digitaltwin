"""Procurement API — supplier request lists, orders, and receiving into stock."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_role
from app.core.enums import Role
from app.models.user import User
from app.services import procurement

router = APIRouter(tags=["procurement"], prefix="/purchases")


class RequestLine(BaseModel):
    product_id: int | None = None
    description: str | None = None
    quantity: float = Field(gt=0)
    unit_cost: float = 0


class RequestCreate(BaseModel):
    supplier_id: int | None = None
    currency: str = "NGN"
    purchase_date: date | None = None
    lines: list[RequestLine] = Field(min_length=1)


class StatusUpdate(BaseModel):
    status: str


class ReceiveRequest(BaseModel):
    warehouse_id: int
    transport_cost: float = 0
    received_date: date | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_request(
    payload: RequestCreate,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF)),
) -> dict:
    r = procurement.create_request(
        db, supplier_id=payload.supplier_id, currency=payload.currency,
        purchase_date=payload.purchase_date,
        lines=[ln.model_dump() for ln in payload.lines], user_id=user.id,
    )
    if r["status"] == "ERROR":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, r["error"])
    return r


@router.get("")
def list_purchases(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="REQUEST | ORDERED | RECEIVED | CANCELLED"),
    supplier_id: int | None = None,
    q: str | None = None,
) -> dict:
    return procurement.list_purchases(db, status=status, supplier_id=supplier_id, q=q,
                                      limit=limit, offset=offset)


@router.get("/{purchase_id}")
def get_purchase(
    purchase_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    r = procurement.get_purchase(db, purchase_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "purchase not found")
    return r


@router.patch("/{purchase_id}/status")
def set_status(
    purchase_id: int,
    payload: StatusUpdate,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.MANAGER)),
) -> dict:
    r = procurement.set_status(db, purchase_id, payload.status)
    if r["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "purchase not found")
    if r["status"] == "ERROR":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, r["error"])
    return r


@router.post("/{purchase_id}/receive")
def receive(
    purchase_id: int,
    payload: ReceiveRequest,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.MANAGER)),
) -> dict:
    r = procurement.receive(
        db, purchase_id=purchase_id, warehouse_id=payload.warehouse_id,
        transport_cost=payload.transport_cost, received_date=payload.received_date,
        user_id=user.id,
    )
    if r["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "purchase not found")
    if r["status"] == "ERROR":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, r["error"])
    return r
