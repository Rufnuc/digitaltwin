"""Waybill — the dispatch record for a sale's goods.

Each waybill is tied to an invoice and captures how the goods left: when they were
sent, who drove/collected them, where to, and any special instructions. It's the
delivery leg of the supply chain, downstream of the invoice.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Lifecycle: raised → goods sent → arrived; or cancelled.
WAYBILL_STATUSES = ("PENDING", "DISPATCHED", "DELIVERED", "CANCELLED")


class Waybill(Base, TimestampMixin):
    __tablename__ = "waybills"

    id: Mapped[int] = mapped_column(primary_key=True)
    waybill_number: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)

    # When the goods actually left (set on dispatch).
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Our own person (apprentice/staff) who carries the goods to the park/station.
    apprentice_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # The transport company/vehicle that carries the goods onward (driver's name is
    # usually not known — we keep the company reference and the phone instead).
    transport_company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    driver_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vehicle_info: Mapped[str | None] = mapped_column(String(128), nullable=True)  # type & plate
    # The park / bus stop / motor station the goods are loaded at.
    station: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Who is collecting / receiving them, and where they're headed.
    receiver_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    receiver_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Anything special (handling, part-delivery, gate pass, etc.).
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
