"""Tests for dividend back-adjustment (G-08)."""
from datetime import date

import pandas as pd
import pytest

from kestrel.data.corporate_actions import (
    DividendEvent,
    StaticDividends,
    adjust_for_dividends,
    adjust_symbol,
)


def _series():
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    # flat at 100 except an ex-div gap down to 90 on the 3rd
    return pd.DataFrame(
        {"open": [100.0, 100.0, 90.0, 90.0], "high": [100.0, 100.0, 90.0, 90.0],
         "low": [100.0, 100.0, 90.0, 90.0], "close": [100.0, 100.0, 90.0, 90.0],
         "volume": [1, 1, 1, 1]},
        index=idx,
    )


def test_no_events_is_unchanged():
    df = _series()
    pd.testing.assert_frame_equal(adjust_for_dividends(df, []), df)


def test_dividend_scales_prices_before_exdate_only():
    df = _series()
    # ₹10 dividend, ex-date 2024-01-03; ref close = 100 (on 01-02) -> factor 0.9
    ev = [DividendEvent("X", date(2024, 1, 3), 10.0)]
    adj = adjust_for_dividends(df, ev)
    # pre-ex bars scaled by 0.9; on/after unchanged
    assert adj.loc["2024-01-02", "close"] == pytest.approx(90.0)
    assert adj.loc["2024-01-01", "close"] == pytest.approx(90.0)
    assert adj.loc["2024-01-03", "close"] == pytest.approx(90.0)   # unchanged
    assert adj.loc["2024-01-04", "close"] == pytest.approx(90.0)
    # the artificial gap between 01-02 and 01-03 is now gone (both 90)


def test_volume_untouched():
    df = _series()
    adj = adjust_for_dividends(df, [DividendEvent("X", date(2024, 1, 3), 10.0)])
    assert list(adj["volume"]) == [1, 1, 1, 1]


def test_event_before_history_is_skipped():
    df = _series()
    adj = adjust_for_dividends(df, [DividendEvent("X", date(2023, 1, 1), 10.0)])
    pd.testing.assert_frame_equal(adj, df)   # no reference close -> no-op


def test_multiple_dividends_compound():
    df = _series()
    evs = [DividendEvent("X", date(2024, 1, 3), 10.0),
           DividendEvent("X", date(2024, 1, 4), 9.0)]  # ref close 90 -> factor 0.9
    adj = adjust_for_dividends(df, evs)
    # 01-02 is before both ex-dates: 100 * 0.9 * 0.9 = 81
    assert adj.loc["2024-01-02", "close"] == pytest.approx(81.0)
    # 01-03 is before only the 01-04 event: 90 * 0.9 = 81
    assert adj.loc["2024-01-03", "close"] == pytest.approx(81.0)
    assert adj.loc["2024-01-04", "close"] == pytest.approx(90.0)  # unchanged


def test_dividend_exceeding_price_is_clamped():
    df = _series()
    adj = adjust_for_dividends(df, [DividendEvent("X", date(2024, 1, 3), 500.0)])
    assert (adj[["open", "high", "low", "close"]] > 0).all().all()   # no negatives


def test_adjust_symbol_uses_source():
    df = _series()
    src = StaticDividends([DividendEvent("X", date(2024, 1, 3), 10.0)])
    adj = adjust_symbol(df, "X", src)
    assert adj.loc["2024-01-02", "close"] == pytest.approx(90.0)
    # a symbol with no events is unchanged
    pd.testing.assert_frame_equal(adjust_symbol(df, "Y", src), df)
