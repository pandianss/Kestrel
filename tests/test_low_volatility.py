"""Tests for the low-volatility factor.

Two properties matter most: it is point-in-time (a score at date t must not
move when future data is appended), and it actually ranks low-vol above
high-vol. Plus a check that the engine runs it through the identical contract
as momentum.
"""
import numpy as np
import pandas as pd

from kestrel.backtest.engine import run_backtest
from kestrel.data.universe import StaticUniverse
from kestrel.strategies import low_volatility as lv


def _panel():
    idx = pd.date_range("2020-01-31", periods=24, freq="ME")
    rng = np.random.RandomState(0)
    # CALM: tiny wobble around a gentle uptrend. WILD: large swings.
    calm = 100 * (1 + 0.01 * rng.randn(24)).cumprod()
    wild = 100 * (1 + 0.10 * rng.randn(24)).cumprod()
    mid = 100 * (1 + 0.04 * rng.randn(24)).cumprod()
    return pd.DataFrame({"CALM": calm, "WILD": wild, "MID": mid}, index=idx)


def test_lowvol_prefers_the_calm_name():
    px = _panel()
    cfg = lv.LowVolConfig(lookback_months=12, min_months=6, n_hold=1)
    scores = lv.lowvol_scores(px, cfg)
    last = scores.iloc[-1]
    # CALM has the least realized vol => highest (least negative) score.
    assert last.idxmax() == "CALM"
    assert lv.target_holdings(last, ["CALM", "WILD", "MID"], cfg) == {"CALM"}


def test_lowvol_scores_are_point_in_time():
    """The score at date t must be identical whether or not later months exist
    — no look-ahead."""
    px = _panel()
    cfg = lv.LowVolConfig(lookback_months=12, min_months=6)
    full = lv.lowvol_scores(px, cfg)
    t = px.index[18]
    truncated = lv.lowvol_scores(px.loc[:t], cfg)
    pd.testing.assert_series_equal(full.loc[t], truncated.loc[t])


def test_lowvol_needs_min_history():
    px = _panel()
    cfg = lv.LowVolConfig(lookback_months=12, min_months=6)
    scores = lv.lowvol_scores(px, cfg)
    # first month has no return; well before min_months everything is NaN.
    assert scores.iloc[0].isna().all()
    assert scores.iloc[-1].notna().all()


def test_engine_runs_lowvol_like_any_factor():
    px = _panel()
    cfg = lv.LowVolConfig(lookback_months=12, min_months=6, n_hold=2)
    res = run_backtest(
        px,
        lv.lowvol_scores(px, cfg),
        StaticUniverse(["CALM", "WILD", "MID"]),
        lambda row, tr: lv.target_holdings(row, tr, cfg),
        min_cross_section=2,
    )
    assert res.survivorship_biased is True          # StaticUniverse says so
    assert res.net.notna().any()                    # produced some returns
