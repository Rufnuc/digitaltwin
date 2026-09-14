"""Stock operations and lot (marker) traceability.

Warehouse CRUD is registered generically in the router; this module carries the
stock movements (receive / transfer / adjust) and the traceability reads. Writes
are role-gated (STAFF+) and audited; reads are open to any authenticated user.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, Role
from app.models.user import User
from app.services import audit, stock

router = APIRouter(tags=["stock"])


class ReceiveRequest(BaseModel):
    product_id: int
    warehouse_id: int
    quantity: int = Field(gt=0)
    unit_cost: float | None = None
    received_date: date | None = None
    supplier_id: int | None = None
    purchase_id: int | None = None
    shipment_ref: str | None = None
    vessel_mmsi: int | None = None
    note: str | None = None


class BatchLine(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_cost: float | None = None
    note: str | None = None


class BatchReceiveRequest(BaseModel):
    warehouse_id: int
    supplier_id: int | None = None
    received_date: date | None = None
    shipment_ref: str | None = None
    vessel_mmsi: int | None = None
    lines: list[BatchLine] = Field(min_length=1)


class TransferRequest(BaseModel):
    product_id: int
    from_warehouse_id: int
    to_warehouse_id: int
    quantity: int = Field(gt=0)
    note: str | None = None


class AdjustRequest(BaseModel):
    lot_id: int
    delta: int
    reason: str


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except stock.StockError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/stock/receive")
def receive(
    payload: ReceiveRequest,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF)),
) -> dict:
    lot = _guard(stock.receive_stock, db, **payload.model_dump(), user_id=user.id)
    audit.record(db, action=AuditAction.CREATE, user_id=user.id, entity_type="stock_lot",
                 entity_id=lot.id, summary=f"received {payload.quantity} into {lot.lot_code}")
    return stock.lot_detail(db, lot.id)


@router.post("/stock/receive-batch")
def receive_batch(
    payload: BatchReceiveRequest,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF)),
) -> dict:
    """Receive a whole delivery from one supplier in a single batch."""
    lots = _guard(
        stock.receive_batch, db, warehouse_id=payload.warehouse_id,
        supplier_id=payload.supplier_id, received_date=payload.received_date,
        shipment_ref=payload.shipment_ref, vessel_mmsi=payload.vessel_mmsi,
        lines=[ln.model_dump() for ln in payload.lines], user_id=user.id,
    )
    audit.record(db, action=AuditAction.CREATE, user_id=user.id, entity_type="stock_batch",
                 summary=f"batch received {len(lots)} lots into warehouse {payload.warehouse_id}")
    return {"received": len(lots),
            "lots": [{"id": lot.id, "lot_code": lot.lot_code, "product_id": lot.product_id,
                      "quantity": lot.quantity_received} for lot in lots]}


@router.post("/stock/transfer")
def transfer(
    payload: TransferRequest,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF)),
) -> dict:
    result = _guard(stock.transfer_stock, db, **payload.model_dump(), user_id=user.id)
    audit.record(db, action=AuditAction.UPDATE, user_id=user.id, entity_type="stock_transfer",
                 summary=f"transferred {payload.quantity} of product {payload.product_id}")
    return result


@router.post("/stock/adjust")
def adjust(
    payload: AdjustRequest,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.MANAGER)),
) -> dict:
    lot = _guard(stock.adjust_lot, db, lot_id=payload.lot_id, delta=payload.delta,
                 reason=payload.reason, user_id=user.id)
    audit.record(db, action=AuditAction.UPDATE, user_id=user.id, entity_type="stock_lot",
                 entity_id=lot.id, summary=f"adjusted {lot.lot_code} by {payload.delta:+d}")
    return stock.lot_detail(db, lot.id)


@router.get("/stock/lots")
def lots(
    _: User = Depends(get_current_user),
    db: Session = Depends(db_session),
    product_id: int | None = Query(None),
    warehouse_id: int | None = Query(None),
    in_stock_only: bool = Query(False),
    limit: int = Query(200, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    return stock.list_lots(db, product_id=product_id, warehouse_id=warehouse_id,
                           in_stock_only=in_stock_only, limit=limit, offset=offset)


@router.get("/stock/lots/{lot_id}")
def lot(lot_id: int, _: User = Depends(get_current_user),
        db: Session = Depends(db_session)) -> dict:
    detail = stock.lot_detail(db, lot_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"lot {lot_id} not found")
    return detail


@router.get("/stock/products/{product_id}/on-hand")
def product_on_hand(product_id: int, _: User = Depends(get_current_user),
                    db: Session = Depends(db_session)) -> dict:
    """Where a product's stock sits across warehouses right now."""
    return {"product_id": product_id, "by_warehouse": stock.on_hand_by_warehouse(db, product_id),
            "provenance": "REAL"}
