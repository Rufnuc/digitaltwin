"""Simulation engine contracts and registry (spec §18).

An engine takes a *structured* scenario request plus a business baseline and
returns structured numeric results. It performs the calculations; the LLM never
does. Phase 1 registers one deterministic engine (price change); Monte Carlo and
the remaining scenario types arrive in Phase 3 behind this same interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.services.analytics import BaselineEconomics


@dataclass
class ScenarioRequest:
    scenario_type: str
    parameters: dict = field(default_factory=dict)
    assumptions: dict = field(default_factory=dict)
    horizon_months: int = 12
    iterations: int = 1


@dataclass
class MetricResult:
    metric: str
    baseline: dict
    scenario: dict
    delta: dict
    detail: str = ""


@dataclass
class ScenarioOutput:
    results: list[MetricResult] = field(default_factory=list)
    assumptions: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    model_name: str = "unset"
    model_version: str = "0.0.0"


class SimulationEngine(Protocol):
    scenario_type: str
    model_name: str
    model_version: str

    def run(self, request: ScenarioRequest, baseline: BaselineEconomics) -> ScenarioOutput: ...


_REGISTRY: dict[str, SimulationEngine] = {}


def register_engine(engine: SimulationEngine) -> None:
    _REGISTRY[engine.scenario_type] = engine


def get_engine(scenario_type: str) -> SimulationEngine | None:
    return _REGISTRY.get(scenario_type)


def registered_scenario_types() -> list[str]:
    return sorted(_REGISTRY.keys())
