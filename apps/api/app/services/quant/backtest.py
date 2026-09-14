"""Rolling-origin backtest and forecast diagnostics (spec v4 §12, §17; v5 §6).

Walk-forward one-step-ahead evaluation: train on the first k periods, forecast the
next, record the error; step forward and repeat. Produces MAE, WAPE, bias, MASE and
interval coverage — the quality evidence the reorder gate uses. Deterministic and
seeded; if too little history exists, returns INSUFFICIENT_DATA rather than a fake
metric.
"""
from __future__ import annotations

from app.services.quant import forecast as fc

MIN_TRAIN = 8      # minimum periods before the first forecast origin
MIN_FOLDS = 3      # need at least this many folds to report metrics


def _point_forecast(train: list[float], pattern: str) -> float:
    if pattern in ("SMOOTH", "ERRATIC"):
        return fc.ses(train)
    if pattern in ("INTERMITTENT", "LUMPY"):
        return fc.sba(train)
    return fc.moving_average(train)


def rolling_origin_backtest(units: list[float], pattern: str, seed: int = 42,
                            max_folds: int = 20) -> dict:
    """One-step-ahead walk-forward metrics for a weekly series."""
    n = len(units)
    if n < MIN_TRAIN + MIN_FOLDS:
        return {"validation_status": "INSUFFICIENT_DATA", "fold_count": 0,
                "reason": f"need >= {MIN_TRAIN + MIN_FOLDS} periods, have {n}"}

    origins = list(range(MIN_TRAIN, n))
    if len(origins) > max_folds:
        origins = origins[-max_folds:]

    errors, actuals, in_p05_p95, in_p25_p75 = [], [], 0, 0
    rng_seed = seed
    for k in origins:
        train = units[:k]
        actual = units[k]
        point = _point_forecast(train, pattern)
        errors.append(point - actual)
        actuals.append(actual)
        # Interval coverage from the fitted predictive distribution at this origin.
        d = fc.forecast(train, pattern, horizon=1, seed=rng_seed, samples=1000)
        q = d.get("quantiles", {})
        if q.get("p05"):
            if q["p05"][0] <= actual <= q["p95"][0]:
                in_p05_p95 += 1
            if q["p25"][0] <= actual <= q["p75"][0]:
                in_p25_p75 += 1
        rng_seed += 1

    folds = len(errors)
    abs_err = [abs(e) for e in errors]
    mae = sum(abs_err) / folds
    total_actual = sum(actuals)
    wape = (sum(abs_err) / total_actual) if total_actual > 0 else None
    bias = sum(errors) / folds
    # MASE denominator: in-sample naive one-step MAE over the whole series.
    naive_err = [abs(units[i] - units[i - 1]) for i in range(1, n)]
    naive_mae = (sum(naive_err) / len(naive_err)) if naive_err else 0.0
    mase = (mae / naive_mae) if naive_mae > 0 else None

    return {
        "validation_status": "OK",
        "fold_count": folds,
        "horizon": 1,
        "mae": round(mae, 6),
        "wape": round(wape, 6) if wape is not None else None,
        "bias": round(bias, 6),
        "mase": round(mase, 6) if mase is not None else None,
        "interval_coverage_p05_p95": round(in_p05_p95 / folds, 6),
        "interval_coverage_p25_p75": round(in_p25_p75 / folds, 6),
        "interval_nominal_p05_p95": 0.90,
        "interval_nominal_p25_p75": 0.50,
        "coverage_sample_count": folds,
    }
