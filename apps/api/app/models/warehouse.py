"""Warehouses, stock lots (traceability markers) and the stock-movement ledger.

Model of record for where physical stock is and where it has been:

  Warehouse       — a storage location the business adds itself; the same product
                    can hold stock in several warehouses at once.
  StockLot        — the "marker": one intake batch of a product into a warehouse,
                    with a scannable lot code, when it was brought in, where it came
                    from (supplier / purchase), landed unit cost, and how much of it
                    is left.
  StockMovement   — every event that changes a lot: RECEIPT, SALE, TRANSFER_OUT /
                    TRANSFER_IN, ADJUSTMENT. The ledger answers who bought a unit
                    (sale → invoice → customer), when it came in, and where it moved.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, ProvenanceMixin, TimestampMixin
from app.models.organization import MONEY


# Movement types (kept as plain strings on the row for portability).
class MovementType:
    RECEIPT = "RECEIPT"            # stock brought into a warehouse (creates a lot)
    SALE = "SALE"                  # sold to a customer via an invoice (draws down a lot)
    TRANSFER_OUT = "TRANSFER_OUT"  # leaving one warehouse in a transfer
    TRANSFER_IN = "TRANSFER_IN"    # arriving in another warehouse in a transfer
    ADJUSTMENT = "ADJUSTMENT"      # manual correction (count, damage, loss)

    ALL = (RECEIPT, SALE, TRANSFER_OUT, TRANSFER_IN, ADJUSTMENT)


class Warehouse(Base, TimestampMixin):
    """A physical storage location. Added and maintained by the business."""

    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    type: Mapped[str] = mapped_column(String(32), default="warehouse")  # warehouse|shop|transit
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)


class StockLot(Base, TimestampMixin, ProvenanceMixin):
    """A traceability marker: one intake batch of a product into a warehouse."""

    __tablename__ = "stock_lots"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_code: Mapped[str] = mapped_column(String(48), unique=True, index=True, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id"), index=True, nullable=False
    )
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id"), nullable=True)
    received_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0)
    quantity_remaining: Mapped[int] = mapped_column(Integer, default=0, index=True)
    unit_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)  # landed cost basis
    # How the goods arrived: a free-text shipment / bill-of-lading reference, and an
    # optional AIS vessel MMSI to link the lot to the voyage on the shipping monitor.
    shipment_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vessel_mmsi: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # IN_STOCK while quantity_remaining > 0, else DEPLETED.
    status: Mapped[str] = mapped_column(String(24), default="IN_STOCK", index=True)
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    movements: Mapped[list[StockMovement]] = relationship(
        back_populates="lot", cascade="all, delete-orphan"
    )


class StockMovement(Base, TimestampMixin):
    """One change to a lot's quantity, with the links that make it traceable."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("stock_lots.id"), index=True, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id"), index=True, nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)  # signed: +in / -out
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # Traceability links.
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(  # who bought it (on a SALE)
        ForeignKey("customers.id"), index=True, nullable=True
    )
    counterparty_warehouse_id: Mapped[int | None] = mapped_column(  # other side of a transfer
        ForeignKey("warehouses.id"), nullable=True
    )
    unit_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # who performed it
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    lot: Mapped[StockLot] = relationship(back_populates="movements")
