"""Tests for the point-in-time fundamentals store and the quality factor."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from kestrel.backtest.engine import run_backtest
from kestrel.data.fundamentals import FundamentalRecord, record_with_lag
from kestrel.data.fundamentals_store import FundamentalsConflictError, FundamentalsStore
from kestrel.data.universe import StaticUniverse
from kestrel.strategies import quality as ql


# ---- store ---------------------------------------------------------------

def test_add_and_asof_roundtrip(tmp_path):
    s = FundamentalsStore(tmp_path)
    r = record_with_lag("X", date(2024, 3, 31), eps_ttm=10, book_value_per_share=100, roe=0.18)
    assert s.add(r) is True
    got = s.asof("X", date(2024, 12, 1))
    assert got is not None and got.roe == 0.18
    assert s.symbols() == ["X"]


def test_reingest_is_idempotent(tmp_path):
    s = FundamentalsStore(tmp_path)
    r = record_with_lag("X", date(2024, 3, 31), 10, 100)
    assert s.add(r) is True
    assert s.add(r) is False          # already present, no-op
    # only one line on disk
    assert len((tmp_path / "X.jsonl").read_text().splitlines()) == 1


def test_conflicting_value_same_key_raises(tmp_path):
    s = FundamentalsStore(tmp_path)
    s.add(FundamentalRecord("X", date(2024, 3, 31), date(2024, 5, 15), 10, 100))
    with pytest.raises(FundamentalsConflictError):
        s.add(FundamentalRecord("X", date(2024, 3, 31), date(2024, 5, 15), 99, 100))


def test_restatement_keeps_both_and_asof_picks_public(tmp_path):
    s = FundamentalsStore(tmp_path)
    # original filing and a later restatement of the SAME quarter
    s.add(FundamentalRecord("X", date(2024, 3, 31), date(2024, 5, 15), eps_ttm=10, book_value_per_share=100))
    s.add(FundamentalRecord("X", date(2024, 3, 31), date(2024, 9, 1), eps_ttm=7, book_value_per_share=100))
    # before the restatement was public, the original stands
    assert s.asof("X", date(2024, 6, 1)).eps_ttm == 10
    # after, the restatement wins
    assert s.asof("X", date(2024, 10, 1)).eps_ttm == 7
    # before anything was public: nothing
    assert s.asof("X", date(2024, 1, 1)) is None


# ---- quality factor ------------------------------------------------------

def test_quality_ranks_high_roe_first():
    idx = pd.date_range("2024-12-31", periods=1, freq="ME")
    prices = pd.DataFrame({"GOOD": [100.0], "POOR": [100.0]}, index=idx)
    s = FundamentalsStore  # not used; build an inline source
    from kestrel.data.fundamentals import StaticFundamentals
    src = StaticFundamentals([
        record_with_lag("GOOD", date(2024, 9, 30), eps_ttm=25, book_value_per_share=100, roe=0.25),
        record_with_lag("POOR", date(2024, 9, 30), eps_ttm=3, book_value_per_share=100, roe=0.03),
    ])
    scores = ql.quality_scores(prices, src, ql.QualityConfig())
    last = scores.iloc[-1]
    assert last["GOOD"] > last["POOR"]
    assert ql.target_holdings(last, ["GOOD", "POOR"], ql.QualityConfig(n_hold=1)) == {"GOOD"}


def test_quality_approximates_roe_when_absent():
    idx = pd.date_range("2024-12-31", periods=1, freq="ME")
    prices = pd.DataFrame({"X": [100.0]}, index=idx)
    from kestrel.data.fundamentals import StaticFundamentals
    # roe not given -> approximated by eps/bvps = 20/100 = 0.20
    src = StaticFundamentals([record_with_lag("X", date(2024, 9, 30), eps_ttm=20, book_value_per_share=100)])
    scores = ql.quality_scores(prices, src, ql.QualityConfig())
    assert scores.iloc[-1]["X"] == pytest.approx(0.20)


def test_store_feeds_quality_asof(tmp_path):
    s = FundamentalsStore(tmp_path)
    s.add(record_with_lag("X", date(2024, 9, 30), eps_ttm=15, book_value_per_share=100, roe=0.15))
    idx = pd.date_range("2025-01-31", periods=1, freq="ME")
    prices = pd.DataFrame({"X": [100.0]}, index=idx)
    scores = ql.quality_scores(prices, s, ql.QualityConfig())   # store IS a FundamentalsSource
    assert scores.iloc[-1]["X"] == pytest.approx(0.15)


def test_engine_runs_quality_like_any_factor():
    idx = pd.date_range("2024-12-31", periods=6, freq="ME")
    rng = np.random.RandomState(3)
    prices = pd.DataFrame({s: 100 * (1 + 0.02 * rng.randn(6)).cumprod()
                           for s in ["A", "B", "C"]}, index=idx)
    from kestrel.data.fundamentals import StaticFundamentals
    src = StaticFundamentals([
        record_with_lag("A", date(2024, 9, 30), 20, 100, roe=0.20),
        record_with_lag("B", date(2024, 9, 30), 10, 100, roe=0.10),
        record_with_lag("C", date(2024, 9, 30), 5, 100, roe=0.05),
    ])
    cfg = ql.QualityConfig(n_hold=2)
    res = run_backtest(prices, ql.quality_scores(prices, src, cfg),
                       StaticUniverse(["A", "B", "C"]),
                       lambda row, tr: ql.target_holdings(row, tr, cfg),
                       min_cross_section=2)
    assert res.net.notna().any()
