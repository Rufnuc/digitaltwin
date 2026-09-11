from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, TimestampsOut


class SimulationCreate(BaseModel):
    name: str
    scenario_type: str
    parameters: dict = Field(default_factory=dict)
    assumptions: dict = Field(default_factory=dict)
    horizon_months: int = 12
    iterations: int = 1


class MonteCarloCreate(BaseModel):
    name: str
    scenario_type: str = "monte_carlo"
    # parameters must include a "distributions" object; see montecarlo spec.
    parameters: dict = Field(default_factory=dict)
    iterations: int = 10000
    horizon_months: int = 12
    target_metric: str = "net_profit"
    target_threshold: float | None = None


class SensitivityRequest(BaseModel):
    parameters: dict = Field(default_factory=dict)
    assumptions: dict = Field(default_factory=dict)
    variations: dict | None = None  # {lever: {low, high}}; defaults applied if omitted
    target_metric: str = "net_profit"


class ScenarioSpec(BaseModel):
    name: str
    parameters: dict = Field(default_factory=dict)
    assumptions: dict = Field(default_factory=dict)


class CompareRequest(BaseModel):
    scenarios: list[ScenarioSpec]


class SimulationResultOut(ORMModel):
    id: int
    metric: str
    baseline: dict | None = None
    scenario: dict | None = None
    delta: dict | None = None
    detail: str | None = None


class SimulationOut(TimestampsOut):
    id: int
    name: str
    scenario_type: str
    parameters: dict
    assumptions: dict
    horizon_months: int
    iterations: int
    status: str
    model_name: str
    model_version: str
    input_data_version: str | None = None
    warnings: list = []
    results: list[SimulationResultOut] = []
