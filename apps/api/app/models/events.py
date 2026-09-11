from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ProvenanceMixin, TimestampMixin


class BusinessEvent(Base, TimestampMixin):
    """Internal business milestones (expansions, closures, policy changes)."""

    __tablename__ = "business_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class MarketEvent(Base, TimestampMixin, ProvenanceMixin):
    """External events (news, regulation). Provenance is mandatory (spec §30)."""

    __tablename__ = "market_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    relevance: Mapped[float | None] = mapped_column(Float, nullable=True)


class EconomicData(Base, TimestampMixin, ProvenanceMixin):
    """Time-series of external economic indicators (inflation, FX, fuel...)."""

    __tablename__ = "economic_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    indicator: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    period: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)


class OwnerKnowledge(Base, TimestampMixin):
    """Subjective owner knowledge (spec §56), stored separately from transactional
    fact and always tagged as such so it is never mistaken for data."""

    __tablename__ = "owner_knowledge"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_entity_id: Mapped[int | None] = mapped_column(nullable=True)
