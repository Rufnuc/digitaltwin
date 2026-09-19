"""Waybills API — raise and track dispatch records against invoices."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_role
from app.core.enums import Role
from app.models.user import User
from app.services import waybills

router = APIRouter(tags=["waybills"], prefix="/waybills")


class WaybillCreate(BaseModel):
    invoice_id: int
    status: str = "PENDING"
    dispatched_at: datetime | None = None
    apprentice_name: str | None = Field(None, max_length=128)
    transport_company: str | None = Field(None, max_length=128)
    driver_phone: str | None = Field(None, max_length=32)
    vehicle_info: str | None = Field(None, max_length=128)
    station: str | None = Field(None, max_length=128)
    receiver_name: str | None = Field(None, max_length=128)
    receiver_phone: str | None = Field(None, max_length=32)
    destination: str | None = Field(None, max_length=255)
    notes: str | None = None


class WaybillUpdate(BaseModel):
    status: str | None = None
    apprentice_name: str | None = Field(None, max_length=128)
    transport_company: str | None = Field(None, max_length=128)
    driver_phone: str | None = Field(None, max_length=32)
    vehicle_info: str | None = Field(None, max_length=128)
    station: str | None = Field(None, max_length=128)
    receiver_name: str | None = Field(None, max_length=128)
    receiver_phone: str | None = Field(None, max_length=32)
    destination: str | None = Field(None, max_length=255)
    notes: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_waybill(
    payload: WaybillCreate,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF)),
) -> dict:
    data = payload.model_dump()
    invoice_id = data.pop("invoice_id")
    r = waybills.create_waybill(db, invoice_id=invoice_id, user_id=user.id, **data)
    if r["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, r["error"])
    if r["status"] == "ERROR":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, r["error"])
    return r


@router.get("")
def list_waybills(
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="PENDING | DISPATCHED | DELIVERED | CANCELLED"),
    invoice_id: int | None = None,
    customer_id: int | None = None,
    q: str | None = Query(None, description="search waybill number"),
) -> dict:
    return waybills.list_waybills(db, status=status, invoice_id=invoice_id,
                                  customer_id=customer_id, q=q, limit=limit, offset=offset)


@router.get("/{waybill_id}")
def get_waybill(
    waybill_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    r = waybills.get_waybill(db, waybill_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "waybill not found")
    return r


@router.patch("/{waybill_id}")
def update_waybill(
    waybill_id: int,
    payload: WaybillUpdate,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    r = waybills.update_waybill(db, waybill_id, payload.model_dump(exclude_unset=True))
    if r["status"] == "NOT_FOUND":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "waybill not found")
    if r["status"] == "ERROR":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, r["error"])
    return r
