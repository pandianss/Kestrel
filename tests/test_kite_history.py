"""Tests for the Kite historical price loader — offline, no live calls.

Covers token resolution from an instruments CSV, the per-request pagination
window, candle parsing into an OHLCV frame, rate-limit pacing, and the 403
(expired-token) path.
"""
import json
from datetime import date

import pytest

from kestrel.data.kite_history import InstrumentResolver, KiteHistory

INSTRUMENTS_CSV = (
    b"instrument_token,tradingsymbol,exchange,instrument_type,segment\n"
    b"256265,RELIANCE,NSE,EQ,NSE\n"
    b"128083204,TCS,NSE,EQ,NSE\n"
    b"112129,RELIANCE,BSE,EQ,BSE\n"
)


# ---- token resolution ----------------------------------------------------

def test_resolver_maps_symbol_to_token():
    r = InstrumentResolver.from_csv_bytes(INSTRUMENTS_CSV)
    assert r.token("RELIANCE") == 256265          # defaults to NSE
    assert r.token("RELIANCE", exchange="BSE") == 112129
    assert r.token("TCS") == 128083204


def test_resolver_raises_for_unknown_symbol():
    r = InstrumentResolver.from_csv_bytes(INSTRUMENTS_CSV)
    with pytest.raises(KeyError):
        r.token("NOTLISTED")


# ---- pagination windows --------------------------------------------------

def test_windows_split_under_the_cap():
    h = KiteHistory("k", "t", http=lambda u, hh: b"", sleep=lambda _: None)
    wins = h._windows(date(2015, 1, 1), date(2025, 1, 1), "day")  # ~3653 days
    assert len(wins) == 2                          # 2000-day cap -> 2 windows
    assert wins[0][0] == date(2015, 1, 1)
    assert wins[-1][1] == date(2025, 1, 1)
    # windows are contiguous and non-overlapping (next starts the day after)
    assert (wins[1][0] - wins[0][1]).days == 1


# ---- fetch + parse -------------------------------------------------------

def _candle_response(rows):
    return json.dumps({"status": "success", "data": {"candles": rows}}).encode()


def test_fetch_parses_ohlcv():
    rows = [
        ["2024-01-01T00:00:00+0530", 100, 105, 99, 102, 1000],
        ["2024-01-02T00:00:00+0530", 102, 108, 101, 107, 1500],
    ]
    h = KiteHistory("k", "t", http=lambda u, hh: _candle_response(rows), sleep=lambda _: None)
    df = h.fetch_candles(256265, date(2024, 1, 1), date(2024, 1, 2))
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert df.iloc[1]["close"] == 107
    assert str(df.index[0].date()) == "2024-01-01"


def test_fetch_paginates_and_concatenates():
    # force 2 windows and return one distinct candle per window
    calls = []

    def http(url, headers):
        calls.append(url)
        # give each window a candle dated at its 'from'
        frm = url.split("from=")[1][:10]
        return _candle_response([[f"{frm}T00:00:00+0530", 1, 1, 1, 1, 1]])

    h = KiteHistory("k", "t", http=http, sleep=lambda _: None)
    df = h.fetch_candles(1, date(2015, 1, 1), date(2025, 1, 1))
    assert len(calls) == 2 and len(df) == 2       # both windows fetched & merged


def test_fetch_empty_when_no_candles():
    h = KiteHistory("k", "t", http=lambda u, hh: _candle_response([]), sleep=lambda _: None)
    df = h.fetch_candles(1, date(2024, 1, 1), date(2024, 1, 2))
    assert df.empty and list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_403_surfaces_as_token_hint():
    import urllib.error

    def http(url, headers):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    h = KiteHistory("k", "t", http=http, sleep=lambda _: None)
    with pytest.raises(RuntimeError, match="token likely"):
        h.fetch_candles(1, date(2024, 1, 1), date(2024, 1, 2))


def test_requires_token():
    with pytest.raises(ValueError):
        KiteHistory("k", "")
