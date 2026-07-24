"""Tests for the value factor and its point-in-time fundamentals.

The property that matters most is look-ahead safety: a fundamental may only be
used once it was *public*, not merely once the period ended. Plus the factor
math (cheap ranks above expensive) and engine integration.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from kestrel.backtest.engine import run_backtest
from kestrel.data.fundamentals import (
    FundamentalRecord,
    StaticFundamentals,
    record_with_lag,
)
from kestrel.data.universe import StaticUniverse
from kestrel.strategies import value as val


def test_publish_before_period_end_is_rejected():
    with pytest.raises(ValueError):
        FundamentalRecord("X", period_end=date(2024, 3, 31),
                          publish_date=date(2024, 3, 1), eps_ttm=5, book_value_per_share=50)


def test_asof_is_point_in_time():
    """A record published after the query date must not be visible."""
    recs = [
        record_with_lag("X", date(2023, 12, 31), eps_ttm=4, book_value_per_share=40),  # pub ~2024-02-14
        record_with_lag("X", date(2024, 3, 31), eps_ttm=6, book_value_per_share=60),   # pub ~2024-05-15
    ]
    src = StaticFundamentals(recs)
    # On 2024-03-01 only the Dec-quarter numbers are public.
    r = src.asof("X", date(2024, 3, 1))
    assert r is not None and r.eps_ttm == 4
    # After the March-quarter filing, the newer numbers win.
    r2 = src.asof("X", date(2024, 6, 1))
    assert r2.eps_ttm == 6
    # Before anything was published: nothing.
    assert src.asof("X", date(2023, 12, 31)) is None


def test_value_ranks_cheap_above_expensive():
    idx = pd.date_range("2024-06-30", periods=1, freq="ME")
    prices = pd.DataFrame({"CHEAP": [100.0], "RICH": [100.0]}, index=idx)
    # Same price; CHEAP earns more per share -> higher earnings yield -> better.
    recs = [
        record_with_lag("CHEAP", date(2024, 3, 31), eps_ttm=20, book_value_per_share=200),
        record_with_lag("RICH", date(2024, 3, 31), eps_ttm=2, book_value_per_share=20),
    ]
    src = StaticFundamentals(recs)
    scores = val.value_scores(prices, src, val.ValueConfig(metric=val.ValueMetric.EARNINGS_YIELD))
    last = scores.iloc[-1]
    assert last["CHEAP"] > last["RICH"]
    assert val.target_holdings(last, ["CHEAP", "RICH"], val.ValueConfig(n_hold=1)) == {"CHEAP"}


def test_value_scores_are_nan_before_fundamentals_public():
    idx = pd.date_range("2024-01-31", periods=1, freq="ME")
    prices = pd.DataFrame({"X": [100.0]}, index=idx)
    # period ends 2023-12-31, publishes ~2024-02-14 -> not public on 2024-01-31
    src = StaticFundamentals([record_with_lag("X", date(2023, 12, 31), 5, 50)])
    scores = val.value_scores(prices, src, val.ValueConfig())
    assert pd.isna(scores.iloc[-1]["X"])


def test_blend_metric_averages_yields():
    idx = pd.date_range("2024-06-30", periods=1, freq="ME")
    prices = pd.DataFrame({"X": [100.0]}, index=idx)
    src = StaticFundamentals([record_with_lag("X", date(2024, 3, 31), eps_ttm=10, book_value_per_share=50)])
    s = val.value_scores(prices, src, val.ValueConfig(metric=val.ValueMetric.BLEND))
    # (10/100 + 50/100) / 2 = 0.30
    assert s.iloc[-1]["X"] == pytest.approx(0.30)


def test_engine_runs_value_like_any_factor():
    idx = pd.date_range("2024-06-30", periods=6, freq="ME")
    rng = np.random.RandomState(1)
    prices = pd.DataFrame(
        {s: 100 * (1 + 0.02 * rng.randn(6)).cumprod() for s in ["A", "B", "C"]}, index=idx
    )
    recs = [
        record_with_lag("A", date(2024, 3, 31), eps_ttm=15, book_value_per_share=150),
        record_with_lag("B", date(2024, 3, 31), eps_ttm=8, book_value_per_share=80),
        record_with_lag("C", date(2024, 3, 31), eps_ttm=3, book_value_per_share=30),
    ]
    src = StaticFundamentals(recs)
    cfg = val.ValueConfig(n_hold=2)
    res = run_backtest(
        prices, val.value_scores(prices, src, cfg),
        StaticUniverse(["A", "B", "C"]),
        lambda row, tr: val.target_holdings(row, tr, cfg),
        min_cross_section=2,
    )
    assert res.survivorship_biased is True
    assert res.net.notna().any()
