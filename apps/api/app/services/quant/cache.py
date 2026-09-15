"""Result cache for the CPU-heavy pure quant computations (speed).

Forecasting and rolling-origin backtesting are pure functions of the demand series
(and a fixed seed), so their output can be safely reused whenever the series is
unchanged. This turns repeat views — reopening a page, re-running a scan, asking
Benfieg the same thing — from "recompute everything" into a dictionary lookup,
without ever serving a stale number: if a product's sales change, the series
changes, the cache key changes, and it recomputes.

Cache entries are keyed by the exact input series, so two products with identical
histories correctly share one result (the maths does not depend on which product).
Call ``clear()`` after a data reload if you want to force recomputation.
"""
from __future__ import annotations

from functools import lru_cache

from app.services.quant import backtest as bt
from app.services.quant import forecast as fc

_MAXSIZE = 8192


@lru_cache(maxsize=_MAXSIZE)
def _forecast(units: tuple[float, ...], pattern: str, horizon: int,
              seed: int, samples: int) -> dict:
    return fc.forecast(list(units), pattern, horizon=horizon, seed=seed, samples=samples)


@lru_cache(maxsize=_MAXSIZE)
def _backtest(units: tuple[float, ...], pattern: str, seed: int) -> dict:
    return bt.rolling_origin_backtest(list(units), pattern, seed=seed)


def cached_forecast(units: list[float], pattern: str, horizon: int = 12,
                    seed: int = 42, samples: int | None = None) -> dict:
    """forecast() with memoisation. The result is READ-ONLY (callers must not
    mutate it — it is shared)."""
    return _forecast(tuple(units), pattern, horizon, seed,
                     samples if samples is not None else fc.DEFAULT_SAMPLES)


def cached_backtest(units: list[float], pattern: str, seed: int = 42) -> dict:
    """rolling_origin_backtest() with memoisation. Result is READ-ONLY."""
    return _backtest(tuple(units), pattern, seed)


def clear() -> None:
    _forecast.cache_clear()
    _backtest.cache_clear()


def stats() -> dict:
    return {"forecast": _forecast.cache_info()._asdict(),
            "backtest": _backtest.cache_info()._asdict()}
