from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ProvenanceMixin, TimestampMixin
from app.models.organization import MONEY


class Product(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    part_number: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)

    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)

    purchase_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    selling_price: Mapped[float | None] = mapped_column(MONEY, nullable=True)

    reorder_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reorder_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # A reference image: either a pasted external URL, or an app path to an
    # uploaded file (/api/v1/products/image/<key>).
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class ProductPriceHistory(Base, TimestampMixin):
    """Append-only record of selling/purchase price changes over time."""

    __tablename__ = "product_price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    purchase_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    selling_price: Mapped[float | None] = mapped_column(MONEY, nullable=True)
