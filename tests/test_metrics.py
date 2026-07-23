"""Tests for performance metrics — especially that t-stat behaves."""
import numpy as np
import pandas as pd

from kestrel.backtest.metrics import information_ratio, perf_stats


def _series(mean, sd, n=120, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-01-31", periods=n, freq="ME")
    return pd.Series(rng.normal(mean, sd, n), index=idx)


def test_too_short_returns_none():
    assert perf_stats(_series(0.01, 0.03, n=12)) is None


def test_positive_drift_positive_cagr():
    s = perf_stats(_series(0.015, 0.03))
    assert s is not None and s.cagr > 0 and s.months == 120


def test_pure_noise_has_small_tstat():
    # zero-mean noise should not look significant
    s = perf_stats(_series(0.0, 0.05, n=240))
    assert abs(s.t_stat) < 2.5


def test_information_ratio_zero_when_identical():
    s = _series(0.01, 0.03)
    ann, ir = information_ratio(s, s.copy())
    assert abs(ann) < 1e-9 and abs(ir) < 1e-9
