from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SimulationStatus
from app.db.base import Base, TimestampMixin


class SimulationRun(Base, TimestampMixin):
    """A stored, reproducible simulation (spec §35/§57/§58).

    Captures scenario parameters, model version and the data version they ran
    against so a past result can always be explained and reproduced.
    """

    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scenario_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    assumptions: Mapped[dict] = mapped_column(JSON, default=dict)
    horizon_months: Mapped[int] = mapped_column(Integer, default=12)
    iterations: Mapped[int] = mapped_column(Integer, default=1)  # >1 once Monte Carlo lands

    model_name: Mapped[str] = mapped_column(String(128), default="unset")
    model_version: Mapped[str] = mapped_column(String(32), default="0.0.0")
    input_data_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default=SimulationStatus.PENDING.value)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    results: Mapped[list[SimulationResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class SimulationResult(Base, TimestampMixin):
    """Structured, machine-produced output. Never authored by an LLM (spec §2)."""

    __tablename__ = "simulation_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_runs.id"), index=True, nullable=False
    )
    metric: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    # All numbers are MODEL_OUTPUT/FORECAST by construction; kept as JSON so
    # deterministic values and percentile distributions share one shape.
    baseline: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scenario: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    delta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[SimulationRun] = relationship(back_populates="results")
