"""Tests for the backtest engine — determinism, no look-ahead, bias propagation.

These are the properties the whole project's credibility rests on (doc 11,
G-23 look-ahead, G-42 reproducibility). Synthetic data with known structure,
so the assertions are exact rather than statistical.
"""
from datetime import date

import numpy as np
import pandas as pd

from kestrel.backtest.engine import run_backtest
from kestrel.data.universe import PointInTimeUniverse, StaticUniverse
from kestrel.strategies.momentum import MomentumConfig, momentum_scores, target_holdings


def _synthetic_prices(n_months=60, n_names=30, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-31", periods=n_months, freq="ME")
    # geometric random walk per name
    rets = rng.normal(0.01, 0.06, size=(n_months, n_names))
    prices = 100 * np.exp(np.cumsum(rets, axis=0))
    return pd.DataFrame(prices, index=idx, columns=[f"S{i:02d}" for i in range(n_names)])


def _run(prices, universe):
    cfg = MomentumConfig(n_hold=5)
    scores = momentum_scores(prices, cfg)
    return run_backtest(
        prices, scores, universe,
        lambda row, tradeable: target_holdings(row, tradeable, cfg),
        min_cross_section=10,
    )


def test_determinism_same_inputs_identical_outputs():
    px = _synthetic_prices()
    uni = StaticUniverse(list(px.columns))
    a = _run(px, uni).monthly
    b = _run(px, uni).monthly
    pd.testing.assert_frame_equal(a, b)


def test_missing_held_return_is_filled_and_counted_not_dropped():
    """G-48: a held name that goes NaN (delisted/suspended) must not silently
    drop out of the mean and shift weight to survivors. It is filled with
    `missing_return` and counted."""
    idx = pd.date_range("2020-01-31", periods=4, freq="ME")
    px = pd.DataFrame({
        "A": [100.0, 110.0, 121.0, 133.1],       # steady riser
        "B": [100.0, 90.0, 81.0, float("nan")],   # delists in the final month
        "C": [100.0, 105.0, 110.0, 115.0],
    }, index=idx)
    scores = pd.DataFrame(1.0, index=idx, columns=px.columns)
    hold_ab = lambda row, tradeable: {s for s in ("A", "B") if s in tradeable}

    res0 = run_backtest(px, scores, StaticUniverse(list(px.columns)), hold_ab,
                        min_cross_section=1, missing_return=0.0)
    resL = run_backtest(px, scores, StaticUniverse(list(px.columns)), hold_ab,
                        min_cross_section=1, missing_return=-1.0)

    assert res0.missing_marks >= 1 and resL.missing_marks == res0.missing_marks
    # the fill value actually changes the realised return — proof it isn't dropped
    assert res0.net.iloc[-1] != resL.net.iloc[-1]


def test_no_lookahead_first_held_month_has_no_return():
    """You cannot earn a return before you have held anything. The first month
    a book exists, its realised gross return must be NaN (the book was only
    just chosen)."""
    px = _synthetic_prices()
    res = _run(px, StaticUniverse(list(px.columns)))
    first_holdings = res.monthly["n_holdings"] > 0
    first_idx = first_holdings.idxmax()
    assert np.isnan(res.monthly.loc[first_idx, "gross"])


def test_costs_reduce_return():
    px = _synthetic_prices()
    res = _run(px, StaticUniverse(list(px.columns)))
    # net <= gross wherever both exist (costs never help)
    both = res.monthly.dropna(subset=["gross", "net"])
    assert (both["net"] <= both["gross"] + 1e-12).all()


def test_survivorship_flag_propagates():
    px = _synthetic_prices()
    assert _run(px, StaticUniverse(list(px.columns))).survivorship_biased is True
    pit = PointInTimeUniverse({date(2015, 1, 1): list(px.columns)})
    assert _run(px, pit).survivorship_biased is False


def test_point_in_time_universe_excludes_future_members():
    px = _synthetic_prices()
    # S00..S14 exist from the start; S15..S29 "list" only from 2017.
    snaps = {
        date(2015, 1, 1): [f"S{i:02d}" for i in range(15)],
        date(2017, 1, 1): [f"S{i:02d}" for i in range(30)],
    }
    pit = PointInTimeUniverse(snaps)
    assert set(pit.members_asof(date(2016, 6, 1))) == {f"S{i:02d}" for i in range(15)}
    assert len(pit.members_asof(date(2018, 1, 1))) == 30
