from __future__ import annotations

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EntityStatus
from app.db.base import Base, TimestampMixin

# Shared money column type (portable across Postgres/SQLite).
MONEY = Numeric(16, 2)


class Branch(Base, TimestampMixin):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=EntityStatus.ACTIVE.value)
    opened_on: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO date


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    monthly_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=EntityStatus.ACTIVE.value)
    hired_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
