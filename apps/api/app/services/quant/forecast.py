"""Forecast models and the PredictiveDistribution object (spec v4 §4–§5, v5 §1/§9).

Point models: naive, moving_average, ses (smooth/erratic); croston, sba, tsb
(intermittent/lumpy). Each forecast returns a PredictiveDistribution — a point
statistic PLUS quantiles derived by sampling the fitted model, never a bare number.

Negative-binomial draws use the NumPy gamma–Poisson mixture (scipy is not a
dependency here; spec v5 §9). All sampling is seeded and reproducible.
"""
from __future__ import annotations

import numpy as np

EPS = 1e-9
DEFAULT_SAMPLES = 2000
_QUANTILES = {"p05": 5, "p25": 25, "p50": 50, "p75": 75, "p95": 95}


# --------------------------------------------------------------------------- #
# Point models — each returns the expected demand per period.
# --------------------------------------------------------------------------- #
def naive(units: list[float]) -> float:
    return float(units[-1]) if units else 0.0


def moving_average(units: list[float], k: int = 4) -> float:
    if not units:
        return 0.0
    window = units[-k:]
    return float(sum(window) / len(window))


def ses(units: list[float], alpha: float = 0.3) -> float:
    if not units:
        return 0.0
    level = units[0]
    for u in units[1:]:
        level = alpha * u + (1 - alpha) * level
    return float(level)


def _croston_components(units: list[float], alpha: float = 0.1) -> tuple[float, float]:
    """Smoothed non-zero size z and inter-demand interval p (Croston)."""
    z = p = None
    since = 1
    for u in units:
        if u > 0:
            z = u if z is None else alpha * u + (1 - alpha) * z
            p = since if p is None else alpha * since + (1 - alpha) * p
            since = 1
        else:
            since += 1
    if z is None:  # no demand at all
        return 0.0, 1.0
    return float(z), float(max(p or 1.0, 1.0))


def croston(units: list[float], alpha: float = 0.1) -> float:
    z, p = _croston_components(units, alpha)
    return z / p


def sba(units: list[float], alpha: float = 0.1) -> float:
    """Syntetos–Boylan Approximation: bias-corrected Croston."""
    z, p = _croston_components(units, alpha)
    return (1 - alpha / 2) * z / p


def tsb(units: list[float], alpha: float = 0.1, beta: float = 0.1) -> tuple[float, float, float]:
    """Teunter–Syntetos–Babai: smooth occurrence probability and size.
    Returns (point_rate, occurrence_prob, size_mean)."""
    prob = 1.0 if (units and units[0] > 0) else 0.0
    size = next((u for u in units if u > 0), 0.0)
    for u in units:
        if u > 0:
            prob = prob + beta * (1 - prob)
            size = size + alpha * (u - size)
        else:
            prob = prob + beta * (0 - prob)
    return float(prob * size), float(min(max(prob, 0.0), 1.0)), float(max(size, 0.0))


# --------------------------------------------------------------------------- #
# Sampling helpers
# --------------------------------------------------------------------------- #
def nbinom_gamma_poisson(
    mu: float, var: float, size: int, rng: np.random.Generator
) -> np.ndarray:
    """Negative-binomial via gamma–Poisson mixture (spec v5 §9). Requires var > mu."""
    r = mu * mu / (var - mu)
    scale = (var - mu) / mu
    lam = rng.gamma(shape=r, scale=scale, size=size)
    return rng.poisson(lam)


def _draw_period_totals(
    family: str, params: dict, samples: int, rng: np.random.Generator
) -> np.ndarray:
    """One period's demand distribution for the chosen family."""
    if family == "POISSON":
        return rng.poisson(max(params["mu"], 0.0), size=samples)
    if family == "NEGATIVE_BINOMIAL":
        return nbinom_gamma_poisson(params["mu"], params["var"], samples, rng)
    if family == "OCCURRENCE_SIZE":
        # Bernoulli occurrence × conditional size (Croston/SBA/TSB bridge, v5 §1).
        occ = rng.random(samples) < params["q"]
        size_mean = max(params["size_mean"], EPS)
        # Geometric-ish conditional size around the mean (non-negative).
        sizes = rng.poisson(size_mean, size=samples) + 1
        return np.where(occ, sizes, 0)
    if family == "EMPIRICAL":
        pool = np.array(params["pool"], dtype=float)
        return rng.choice(pool, size=samples, replace=True)
    # NONE — degenerate point mass.
    return np.full(samples, max(params.get("mu", 0.0), 0.0))


def _quantiles(sample: np.ndarray) -> dict:
    return {name: round(float(np.percentile(sample, q)), 4) for name, q in _QUANTILES.items()}


# --------------------------------------------------------------------------- #
# Predictive distribution assembly
# --------------------------------------------------------------------------- #
def _dispersion_family(nz: list[float]) -> tuple[str, dict]:
    """Choose Poisson vs negative-binomial for smooth demand (spec v4 §5.1)."""
    if len(nz) < 10:
        mu = (sum(nz) / len(nz)) if nz else 0.0
        return "POISSON", {"mu": mu}
    mu = sum(nz) / len(nz)
    var = sum((x - mu) ** 2 for x in nz) / len(nz)
    if var > 1.25 * mu and var > mu:
        return "NEGATIVE_BINOMIAL", {"mu": mu, "var": var}
    return "POISSON", {"mu": mu}


def forecast(units: list[float], pattern: str, horizon: int = 12, seed: int = 42,
             samples: int = DEFAULT_SAMPLES) -> dict:
    """Route to the right model for the pattern and return a PredictiveDistribution."""
    rng = np.random.default_rng(seed)
    warnings: list[str] = []
    nz = [u for u in units if u > 0]

    if pattern in ("SMOOTH", "ERRATIC"):
        point = ses(units)
        family, params = _dispersion_family(nz)
        model = "ses"
    elif pattern in ("INTERMITTENT", "LUMPY"):
        point = sba(units)
        z, p = _croston_components(units)
        q = min(1.0 / max(p, 1.0), 1.0)
        # Calibrate conditional size to preserve expected demand (spec v5 §1) with a cap.
        size_mean = min(max(z, 0.0), (max(nz) if nz else 1.0))
        family, params = "OCCURRENCE_SIZE", {"q": q, "size_mean": size_mean}
        model = "sba"
    else:
        return {
            "product_pattern": pattern, "point_statistic": "MEAN", "point_values": [0.0] * horizon,
            "quantiles": {k: [0.0] * horizon for k in _QUANTILES},
            "distribution_family": "NONE", "model_name": "none", "sample_count": 0,
            "seed": seed, "horizon_periods": horizon, "frequency": "WEEKLY",
            "warnings": ["NO_SALES_HISTORY"],
        }

    if len(nz) < 10:
        warnings.append("LOW_EVIDENCE")

    per_period = _draw_period_totals(family, params, samples, rng)
    point_val = round(float(point), 4)
    q_single = _quantiles(per_period)
    quantiles = {k: [q_single[k]] * horizon for k in _QUANTILES}
    return {
        "product_pattern": pattern,
        "frequency": "WEEKLY",
        "horizon_periods": horizon,
        "point_statistic": "MEAN",
        "point_values": [point_val] * horizon,
        "quantiles": quantiles,
        "distribution_family": family,
        "distribution_parameters": {
            k: round(v, 6) for k, v in params.items() if isinstance(v, int | float)
        },
        "model_name": model,
        "model_version": f"{model}-1.0.0",
        "sample_count": samples,
        "seed": seed,
        "warnings": warnings,
    }
