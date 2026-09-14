"""Point-forecast models for the demand series (Quant Phase 1).

Each model consumes an aligned per-period demand series (oldest → newest) and
returns a `ModelFit` carrying the per-period point rate plus the internal state a
predictive-distribution bridge needs (Croston/SBA/TSB occurrence prob and size).

Intermittent models follow the standard definitions:
  Croston  f = z/p                          (SES-smoothed size z, interval p)
  SBA      f = (1 - alpha/2) * z/p          (Syntetos–Boylan bias correction)
  TSB      f = prob * size                  (occurrence prob updated every period)

Smoothing constants default to alpha=0.1 (level/size) and beta=0.05 (TSB
occurrence); they are ASSUMPTIONS returned with the fit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_ALPHA = 0.1
_BETA = 0.05


@dataclass
class ModelFit:
    model: str
    point_rate: float               # expected demand per period
    params: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def naive(series: list[float]) -> ModelFit:
    return ModelFit("naive", float(series[-1]) if series else 0.0)


def moving_average(series: list[float], window: int = 4) -> ModelFit:
    if not series:
        return ModelFit("moving_average", 0.0, {"window": window})
    w = series[-window:]
    return ModelFit("moving_average", sum(w) / len(w), {"window": min(window, len(series))})


def ses(series: list[float], alpha: float = _ALPHA) -> ModelFit:
    """Simple exponential smoothing; the last level is the forecast rate."""
    if not series:
        return ModelFit("ses", 0.0, {"alpha": alpha})
    level = series[0]
    for x in series[1:]:
        level = alpha * x + (1 - alpha) * level
    return ModelFit("ses", float(level), {"alpha": alpha})


def _croston_state(series: list[float], alpha: float) -> tuple[float, float, list[float]]:
    """Return smoothed size z, interval p, and the non-zero sizes seen."""
    nonzero = [v for v in series if v > 0]
    if not nonzero:
        return 0.0, 1.0, []
    z = nonzero[0]
    # Initial interval: mean gap between demands, at least 1.
    idxs = [i for i, v in enumerate(series) if v > 0]
    p = ((idxs[-1] - idxs[0]) / (len(idxs) - 1)) if len(idxs) > 1 else 1.0
    p = max(p, 1.0)
    q = 1
    started = False
    for v in series:
        if v > 0:
            if started:
                z = alpha * v + (1 - alpha) * z
                p = alpha * q + (1 - alpha) * p
            started = True
            q = 1
        else:
            q += 1
    return z, max(p, 1.0), nonzero


def croston(series: list[float], alpha: float = _ALPHA) -> ModelFit:
    z, p, nz = _croston_state(series, alpha)
    rate = z / p if p else 0.0
    return ModelFit("croston", rate, {"alpha": alpha, "z_t": round(z, 6), "p_t": round(p, 6),
                                      "nonzero_count": len(nz)})


def sba(series: list[float], alpha: float = _ALPHA) -> ModelFit:
    z, p, nz = _croston_state(series, alpha)
    rate = (1 - alpha / 2) * (z / p) if p else 0.0
    q_week = min(1.0 / max(p, 1.0), 1.0)
    return ModelFit("sba", rate, {"alpha": alpha, "z_t": round(z, 6), "p_t": round(p, 6),
                                  "occurrence_probability": round(q_week, 6),
                                  "size_mean": round(z, 6), "nonzero_count": len(nz)})


def tsb(series: list[float], alpha: float = _ALPHA, beta: float = _BETA) -> ModelFit:
    """Teunter–Syntetos–Babai: occurrence probability updated every period."""
    nonzero = [v for v in series if v > 0]
    if not nonzero:
        return ModelFit("tsb", 0.0, {"alpha": alpha, "beta": beta,
                                     "occurrence_probability": 0.0, "size_mean": 0.0})
    prob = len(nonzero) / len(series)
    size = nonzero[0]
    for v in series:
        if v > 0:
            prob = prob + beta * (1 - prob)
            size = size + alpha * (v - size)
        else:
            prob = prob + beta * (0 - prob)
    prob = min(max(prob, 0.0), 1.0)
    size = max(size, 0.0)
    return ModelFit("tsb", prob * size, {"alpha": alpha, "beta": beta,
                                         "occurrence_probability": round(prob, 6),
                                         "size_mean": round(size, 6),
                                         "nonzero_count": len(nonzero)})


_REGISTRY = {
    "naive": naive, "moving_average": moving_average, "ses": ses,
    "croston": croston, "sba": sba, "tsb": tsb,
}


def fit(model: str, series: list[float]) -> ModelFit:
    fn = _REGISTRY.get(model)
    if fn is None:
        raise ValueError(f"unknown forecast model '{model}'")
    return fn(series)
