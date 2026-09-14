"""Quant Phase 1 — rolling-origin backtest diagnostics."""
from __future__ import annotations

from app.services.quant import backtest as bt


def test_insufficient_data():
    r = bt.rolling_origin_backtest([1, 2, 3], "SMOOTH")
    assert r["validation_status"] == "INSUFFICIENT_DATA"
    assert r["fold_count"] == 0


def test_perfect_constant_series_has_zero_error():
    # A constant series -> SES predicts the constant exactly -> zero MAE/WAPE/bias.
    r = bt.rolling_origin_backtest([5.0] * 20, "SMOOTH")
    assert r["validation_status"] == "OK"
    assert r["fold_count"] >= bt.MIN_FOLDS
    assert r["mae"] == 0.0
    assert r["wape"] == 0.0
    assert r["bias"] == 0.0


def test_metrics_present_and_bounded():
    units = [5, 6, 4, 7, 5, 6, 5, 4, 6, 5, 7, 5, 6, 4, 5, 6, 5, 6, 4, 7]
    r = bt.rolling_origin_backtest(units, "SMOOTH")
    assert r["validation_status"] == "OK"
    assert r["mae"] >= 0
    assert 0.0 <= r["interval_coverage_p05_p95"] <= 1.0
    assert r["mase"] is not None
    assert r["coverage_sample_count"] == r["fold_count"]


def test_reproducible():
    units = [0, 0, 3, 0, 0, 3, 0, 2, 0, 0, 4, 0, 0, 3, 0]
    a = bt.rolling_origin_backtest(units, "INTERMITTENT", seed=11)
    b = bt.rolling_origin_backtest(units, "INTERMITTENT", seed=11)
    assert a == b
