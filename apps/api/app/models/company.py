from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CompanyProfile(Base, TimestampMixin):
    """The business's own details, printed on invoices and documents. A single row
    (id = 1); editable by owners in Settings."""

    __tablename__ = "company_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    name: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    footer_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
