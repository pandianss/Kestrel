"""Tests for fundamental trend analysis (improving vs declining)."""
from datetime import date

import pytest

from kestrel.analysis.fundamentals_trend import analyse, build_series, compare, company_trend
from kestrel.data.fundamentals import FundamentalRecord, record_with_lag
from kestrel.data.fundamentals_store import FundamentalsStore

QE = [date(2023, 3, 31), date(2023, 6, 30), date(2023, 9, 30), date(2023, 12, 31),
      date(2024, 3, 31)]


def _recs(sym, eps_series):
    return [record_with_lag(sym, qe, eps_ttm=e, book_value_per_share=100)
            for qe, e in zip(QE, eps_series)]


def test_rising_eps_is_improving():
    t = analyse("UP", _recs("UP", [5, 6, 7, 8, 9]))
    assert t.direction == "improving" and t.slope > 0
    assert t.qoq_change == pytest.approx(1.0)


def test_falling_eps_is_declining():
    t = analyse("DN", _recs("DN", [9, 8, 7, 6, 5]))
    assert t.direction == "declining" and t.slope < 0


def test_flat_eps_is_flat():
    t = analyse("FL", _recs("FL", [5.0, 5.01, 4.99, 5.0, 5.0]))
    assert t.direction == "flat"


def test_single_point_is_insufficient():
    t = analyse("ONE", _recs("ONE", [5])[:1])
    assert t.direction == "insufficient" and t.latest_eps == 5


def test_yoy_growth_vs_same_quarter_last_year():
    # 5 quarters: Mar23=5 ... Mar24=10 -> YoY +100%
    t = analyse("Y", _recs("Y", [5, 6, 7, 8, 10]))
    assert t.yoy_growth == pytest.approx(1.0)


def test_negative_eps_direction_defined_growth_none():
    # loss narrowing: -5 -> -1 is improving; qoq_growth None (prev < 0)
    t = analyse("LOSS", _recs("LOSS", [-5, -4, -3, -2, -1]))
    assert t.direction == "improving"
    assert t.qoq_growth is None       # base negative -> % undefined
    assert t.qoq_change == pytest.approx(1.0)


def test_build_series_uses_latest_restatement_and_asof():
    recs = [
        FundamentalRecord("X", date(2024, 3, 31), date(2024, 5, 15), eps_ttm=10, book_value_per_share=100),
        FundamentalRecord("X", date(2024, 3, 31), date(2024, 9, 1), eps_ttm=7, book_value_per_share=100),  # restated
    ]
    # full history -> restated value wins
    assert build_series(recs)[0].eps == 7
    # as of before the restatement -> original value
    assert build_series(recs, asof=date(2024, 6, 1))[0].eps == 10


def test_compare_ranks_improving_first(tmp_path):
    store = FundamentalsStore(tmp_path)
    for r in _recs("UP", [5, 6, 7, 8, 9]) + _recs("DN", [9, 8, 7, 6, 5]):
        store.add(r)
    ranked = compare(store)
    assert [t.symbol for t in ranked] == ["UP", "DN"]
    assert ranked[0].direction == "improving" and ranked[1].direction == "declining"


def test_company_trend_from_store(tmp_path):
    store = FundamentalsStore(tmp_path)
    for r in _recs("Z", [3, 4, 5]):
        store.add(r)
    assert company_trend(store, "Z").direction == "improving"
