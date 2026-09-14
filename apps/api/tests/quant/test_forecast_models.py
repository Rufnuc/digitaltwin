"""Quant Phase 1: point-forecast model behaviour."""
from __future__ import annotations

from app.services.quant import forecast_models as fm


def test_naive_is_last_value():
    assert fm.naive([1, 2, 3, 9]).point_rate == 9.0


def test_moving_average_window():
    r = fm.moving_average([2, 4, 6, 8], window=2)
    assert r.point_rate == 7.0  # mean of last 2 = (6+8)/2
    assert r.params["window"] == 2


def test_ses_converges_toward_series():
    # Constant series -> SES level equals the constant.
    assert abs(fm.ses([5, 5, 5, 5, 5]).point_rate - 5.0) < 1e-9


def test_croston_rate_on_regular_intermittent():
    # Demand of 4 every 4 periods -> rate ~ 4/4 = 1.0.
    series = [0, 0, 0, 4, 0, 0, 0, 4, 0, 0, 0, 4]
    r = fm.croston(series)
    assert 0.8 <= r.point_rate <= 1.2
    assert r.params["p_t"] >= 1.0


def test_sba_below_croston():
    series = [0, 0, 0, 4, 0, 0, 0, 4, 0, 0, 0, 4]
    c = fm.croston(series).point_rate
    s = fm.sba(series).point_rate
    assert s < c  # SBA applies the (1 - alpha/2) deflation


def test_tsb_occurrence_and_size():
    series = [0, 0, 3, 0, 0, 3, 0, 0, 3]
    r = fm.tsb(series)
    assert 0.0 < r.params["occurrence_probability"] <= 1.0
    assert r.params["size_mean"] > 0
    # expected demand = prob * size, positive and modest
    assert 0.0 < r.point_rate < 3.0


def test_empty_series_is_zero():
    for m in ("naive", "moving_average", "ses", "croston", "sba", "tsb"):
        assert fm.fit(m, []).point_rate == 0.0


def test_unknown_model_raises():
    import pytest
    with pytest.raises(ValueError):
        fm.fit("nope", [1, 2, 3])
