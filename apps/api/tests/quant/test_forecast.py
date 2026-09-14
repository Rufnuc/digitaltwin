"""Quant Phase 1 — forecast models + PredictiveDistribution."""
from __future__ import annotations

import numpy as np

from app.services.quant import forecast as fc


def test_naive_and_moving_average():
    assert fc.naive([1, 2, 3]) == 3.0
    assert fc.moving_average([2, 4, 6, 8], k=2) == 7.0
    assert fc.moving_average([2, 4, 6, 8]) == 5.0  # default k=4


def test_ses_converges_to_level():
    # Constant series -> SES equals the constant.
    assert abs(fc.ses([5, 5, 5, 5, 5]) - 5.0) < 1e-9


def test_sba_is_bias_corrected_croston():
    units = [0, 0, 3, 0, 0, 3, 0, 0, 3]
    c = fc.croston(units)
    s = fc.sba(units)
    assert s < c  # SBA applies the (1 - alpha/2) shrinkage
    z, p = fc._croston_components(units)
    assert p > 1.0  # inter-demand interval detected


def test_tsb_components():
    point, q, size = fc.tsb([0, 0, 2, 0, 0, 2, 0, 0, 2])
    assert 0.0 <= q <= 1.0
    assert size > 0
    assert abs(point - q * size) < 1e-9


def test_nbinom_moments_match_target():
    # spec v5 §9: sampler mean/variance must match target within tolerance.
    rng = np.random.default_rng(7)
    mu, var = 5.0, 12.0
    draws = fc.nbinom_gamma_poisson(mu, var, 200_000, rng)
    assert abs(draws.mean() - mu) < 0.15
    assert abs(draws.var() - var) < 0.6


def test_forecast_smooth_returns_predictive_distribution():
    d = fc.forecast([5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6], "SMOOTH", horizon=12)
    assert d["point_statistic"] == "MEAN"
    assert len(d["point_values"]) == 12
    assert set(d["quantiles"]) == {"p05", "p25", "p50", "p75", "p95"}
    assert d["distribution_family"] in ("POISSON", "NEGATIVE_BINOMIAL")
    # quantiles are ordered p05 <= p50 <= p95
    assert d["quantiles"]["p05"][0] <= d["quantiles"]["p50"][0] <= d["quantiles"]["p95"][0]


def test_forecast_intermittent_uses_occurrence_size():
    d = fc.forecast([0, 0, 3, 0, 0, 3, 0, 0, 3, 0, 0, 3], "INTERMITTENT", horizon=8)
    assert d["distribution_family"] == "OCCURRENCE_SIZE"
    assert d["model_name"] == "sba"
    assert d["point_values"][0] > 0


def test_forecast_no_evidence():
    d = fc.forecast([0, 0, 0], "NO_EVIDENCE")
    assert d["distribution_family"] == "NONE"
    assert "NO_SALES_HISTORY" in d["warnings"]


def test_forecast_is_reproducible():
    a = fc.forecast([0, 0, 3, 0, 0, 3, 0, 0, 3], "INTERMITTENT", seed=99)
    b = fc.forecast([0, 0, 3, 0, 0, 3, 0, 0, 3], "INTERMITTENT", seed=99)
    assert a["quantiles"] == b["quantiles"]
