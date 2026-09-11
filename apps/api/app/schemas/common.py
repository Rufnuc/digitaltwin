from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProvenanceOut(ORMModel):
    """Provenance fields surfaced on every business record read model."""

    data_origin: str
    verification_status: str
    confidence: float | None = None


class TimestampsOut(ORMModel):
    created_at: datetime
    updated_at: datetime


class Page(BaseModel):
    """Simple pagination envelope (spec §44 — never dump whole datasets)."""

    total: int
    limit: int
    offset: int
