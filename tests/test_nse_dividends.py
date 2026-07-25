"""Tests for the NSE dividend feed (parsing + adjustment integration)."""
import json
from datetime import date

from kestrel.data.nse_dividends import NSEDividendSource, parse_dividend_events


ROWS = [
    {"symbol": "RELIANCE", "series": "EQ", "subject": "Dividend - Rs 6 Per Share", "exDate": "05-Jun-2026"},
    {"symbol": "RELIANCE", "series": "EQ", "subject": "Interim Dividend Rs. 5.50 Per Share", "exDate": "14-Aug-2025"},
    {"symbol": "RELIANCE", "series": "EQ", "subject": "Bonus 1:1", "exDate": "10-Oct-2017"},   # not a dividend
    {"symbol": "RELIANCE", "series": "EQ", "subject": "Face Value Split", "exDate": "01-Jan-2020"},  # not a dividend
    {"symbol": "RELIANCE", "series": "EQ", "subject": "Annual General Meeting", "exDate": "bad"},  # unparseable
]


def test_parse_only_dividends_with_amounts():
    evs = parse_dividend_events("RELIANCE", ROWS)
    assert len(evs) == 2
    assert evs[0].amount_per_share == 6.0 and evs[0].ex_date == date(2026, 6, 5)
    assert evs[1].amount_per_share == 5.5 and evs[1].ex_date == date(2025, 8, 14)


def test_source_events_via_injected_http():
    src = NSEDividendSource(http=lambda url: json.dumps(ROWS).encode())
    evs = src.events("RELIANCE")
    assert [e.amount_per_share for e in evs] == [6.0, 5.5]


def test_source_handles_data_wrapper():
    src = NSEDividendSource(http=lambda url: json.dumps({"data": ROWS}).encode())
    assert len(src.events("RELIANCE")) == 2


def test_feeds_dividend_adjustment():
    import pandas as pd
    from kestrel.data.corporate_actions import adjust_for_dividends

    idx = pd.to_datetime(["2025-08-13", "2025-08-14"])
    df = pd.DataFrame({"open": [100.0, 94.5], "high": [100.0, 94.5],
                       "low": [100.0, 94.5], "close": [100.0, 94.5], "volume": [1, 1]}, index=idx)
    src = NSEDividendSource(http=lambda url: json.dumps(
        [{"subject": "Dividend - Rs 5.50 Per Share", "exDate": "14-Aug-2025"}]).encode())
    adj = adjust_for_dividends(df, src.events("RELIANCE"))
    # pre-ex close 100 scaled by (100-5.5)/100 = 0.945 -> 94.5, matching the ex-day
    assert adj.loc["2025-08-13", "close"] == 94.5
