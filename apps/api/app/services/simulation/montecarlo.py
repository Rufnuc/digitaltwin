"""Monte Carlo simulation (spec §20).

Samples uncertain scenario variables from declared probability distributions,
projects the P&L for each draw with the shared deterministic model, and reports
the *distribution* of outcomes — never a single number presented as certainty.

Distribution spec per variable (dict):
    {"type": "fixed",      "value": x}
    {"type": "normal",     "mean": m, "std": s}
    {"type": "uniform",    "low": a, "high": b}
    {"type": "triangular", "low": a, "mode": c, "high": b}

Variables: price_pct, demand_pct, unit_cost_pct, fixed_opex_delta, elasticity.
"""
from __future__ import annotations

import numpy as np

from app.services.analytics import BaselineEconomics
from app.services.simulation.model import Levers, project

VARIABLES = ("price_pct", "demand_pct", "unit_cost_pct", "fixed_opex_delta", "elasticity")
_PERCENTILES = (5, 25, 50, 75, 95)


def _sample(spec: dict | float | int | None, n: int, rng: np.random.Generator) -> np.ndarray:
    if spec is None:
        return np.zeros(n)
    if isinstance(spec, int | float):
        return np.full(n, float(spec))
    kind = spec.get("type", "fixed")
    if kind == "fixed":
        return np.full(n, float(spec.get("value", 0.0)))
    if kind == "normal":
        return rng.normal(float(spec["mean"]), max(float(spec["std"]), 0.0), n)
    if kind == "uniform":
        return rng.uniform(float(spec["low"]), float(spec["high"]), n)
    if kind == "triangular":
        return rng.triangular(float(spec["low"]), float(spec["mode"]), float(spec["high"]), n)
    raise ValueError(f"Unknown distribution type '{kind}'")


def _percentile_block(arr: np.ndarray) -> dict:
    pcts = {f"p{p}": round(float(np.percentile(arr, p)), 2) for p in _PERCENTILES}
    return {
        "mean": round(float(arr.mean()), 2),
        "std": round(float(arr.std()), 2),
        "min": round(float(arr.min()), 2),
        "max": round(float(arr.max()), 2),
        **pcts,
    }


def run_monte_carlo(
    baseline: BaselineEconomics,
    distributions: dict,
    iterations: int = 10000,
    seed: int = 42,
    target_metric: str = "net_profit",
    target_threshold: float | None = None,
) -> dict:
    iterations = max(100, min(int(iterations), 200_000))
    rng = np.random.default_rng(seed)

    # Sample each variable (varying ones get arrays; others are constant).
    samples = {v: _sample(distributions.get(v), iterations, rng) for v in VARIABLES}

    # Vectorised projection would be faster, but per-draw keeps one source of
    # truth (the shared `project`). Iterations are capped, so this is fine.
    metrics = {"revenue": [], "gross_profit": [], "gross_margin": [], "net_profit": [], "units": []}
    for i in range(iterations):
        levers = Levers(
            price_pct=samples["price_pct"][i],
            demand_pct=samples["demand_pct"][i],
            unit_cost_pct=samples["unit_cost_pct"][i],
            fixed_opex_delta=samples["fixed_opex_delta"][i],
            elasticity=samples["elasticity"][i],
        )
        p = project(baseline, levers)
        for m in metrics:
            metrics[m].append(p.metric(m))
    metric_arrays = {m: np.asarray(v) for m, v in metrics.items()}

    target = metric_arrays[target_metric]
    prob_loss = float((metric_arrays["net_profit"] < 0).mean())
    prob_target = (
        float((target >= target_threshold).mean()) if target_threshold is not None else None
    )

    # Input sensitivity: correlation of each *varying* input with the target.
    sensitivity = []
    for v in VARIABLES:
        s = samples[v]
        if s.std() > 1e-12:  # only inputs that actually varied
            corr = float(np.corrcoef(s, target)[0, 1])
            sensitivity.append({"variable": v, "correlation": round(corr, 4)})
    sensitivity.sort(key=lambda d: abs(d["correlation"]), reverse=True)

    return {
        "iterations": iterations,
        "seed": seed,
        "target_metric": target_metric,
        "distributions_by_metric": {m: _percentile_block(a) for m, a in metric_arrays.items()},
        "probability_of_loss": round(prob_loss, 4),
        "probability_of_target": None if prob_target is None else round(prob_target, 4),
        "target_threshold": target_threshold,
        "sensitivity": sensitivity,
        "provenance": "FORECAST",
    }
