"""Orchestrates a simulation run: baseline → engine → persisted results (spec §35)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.enums import SimulationStatus
from app.models.simulation import SimulationResult, SimulationRun
from app.services.analytics import baseline_economics
from app.services.simulation import engines, price_change  # noqa: F401  (register engines)
from app.services.simulation.base import ScenarioRequest, get_engine
from app.services.simulation.model import REPORT_METRICS, Levers, project
from app.services.simulation.montecarlo import run_monte_carlo


def run_simulation(db: Session, run: SimulationRun) -> SimulationRun:
    engine = get_engine(run.scenario_type)
    if engine is None:
        run.status = SimulationStatus.FAILED.value
        run.warnings = [f"No engine registered for scenario_type '{run.scenario_type}'."]
        db.commit()
        db.refresh(run)
        return run

    run.status = SimulationStatus.RUNNING.value
    db.commit()

    baseline = baseline_economics(db)
    request = ScenarioRequest(
        scenario_type=run.scenario_type,
        parameters=run.parameters or {},
        assumptions=run.assumptions or {},
        horizon_months=run.horizon_months,
        iterations=run.iterations,
    )
    output = engine.run(request, baseline)

    # Replace any prior results (reproducible re-runs).
    for old in list(run.results):
        db.delete(old)
    for r in output.results:
        db.add(
            SimulationResult(
                run_id=run.id,
                metric=r.metric,
                baseline=r.baseline,
                scenario=r.scenario,
                delta=r.delta,
                detail=r.detail,
            )
        )

    run.assumptions = output.assumptions
    run.warnings = output.warnings
    run.model_name = output.model_name
    run.model_version = output.model_version
    run.input_data_version = f"invoices_rev={baseline.revenue:.2f}"
    run.status = SimulationStatus.COMPLETED.value
    db.commit()
    db.refresh(run)
    return run


def run_monte_carlo_simulation(
    db: Session,
    run: SimulationRun,
    target_metric: str = "net_profit",
    target_threshold: float | None = None,
) -> SimulationRun:
    """Persist a Monte Carlo run: per-metric percentile distributions + summary.

    Uncertainty distributions are read from `run.parameters["distributions"]`
    (see montecarlo.VARIABLES / distribution spec). Each metric result stores the
    deterministic baseline value and the sampled percentile block (FORECAST).
    """
    run.status = SimulationStatus.RUNNING.value
    db.commit()

    baseline = baseline_economics(db)
    base = project(baseline, Levers())
    distributions = (run.parameters or {}).get("distributions", {})
    mc = run_monte_carlo(
        baseline,
        distributions,
        iterations=run.iterations,
        target_metric=target_metric,
        target_threshold=target_threshold,
    )

    for old in list(run.results):
        db.delete(old)
    for metric in REPORT_METRICS:
        block = mc["distributions_by_metric"][metric]
        base_val = round(base.metric(metric), 4 if metric == "gross_margin" else 2)
        db.add(
            SimulationResult(
                run_id=run.id,
                metric=metric,
                baseline={"value": base_val},
                scenario=block,  # full percentile distribution
                delta={"expected": block["mean"], "p5": block["p5"], "p95": block["p95"]},
                detail="Monte Carlo percentile distribution.",
            )
        )

    run.assumptions = {
        **(run.assumptions or {}),
        "monte_carlo": {
            "iterations": mc["iterations"],
            "seed": mc["seed"],
            "target_metric": mc["target_metric"],
            "probability_of_loss": mc["probability_of_loss"],
            "probability_of_target": mc["probability_of_target"],
            "target_threshold": mc["target_threshold"],
            "sensitivity": mc["sensitivity"],
        },
    }
    run.model_name = "monte_carlo"
    run.model_version = "1.0.0"
    run.input_data_version = f"invoices_rev={baseline.revenue:.2f}"
    run.status = SimulationStatus.COMPLETED.value
    db.commit()
    db.refresh(run)
    return run
