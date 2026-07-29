"""Tests for the incremental history harvester — never re-download what's cached."""
from datetime import date

import pandas as pd

import scripts.harvest_history as hh


class _Resolver:
    def token(self, sym):
        return 1


class _Hist:
    """Fake KiteHistory that records the from-date it was asked for."""
    def __init__(self):
        self.calls = []

    def fetch_candles(self, token, frm, to, *, interval="day"):
        self.calls.append((frm, to))
        idx = pd.date_range(frm, to, freq="D")
        return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                             "volume": 1}, index=idx)


def test_up_to_date_helper():
    assert hh._is_up_to_date(date(2024, 1, 10), date(2024, 1, 10)) is True
    assert hh._is_up_to_date(date(2024, 1, 5), date(2024, 1, 10)) is False   # 5-day gap


def test_full_then_incremental_then_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(hh, "CACHE_DIR", tmp_path)
    res, hist = _Resolver(), _Hist()

    # 1) not cached -> full fetch from the start
    c1 = hh.run_harvest_history(["X"], date(2020, 1, 1), date(2020, 1, 10), hist, res, pause=0, log=lambda *_: None)
    assert c1["fetched"] == 1 and hist.calls[-1][0] == date(2020, 1, 1)

    # 2) cached but stale -> fetch ONLY the missing tail, not the whole history
    hist.calls.clear()
    c2 = hh.run_harvest_history(["X"], date(2020, 1, 1), date(2020, 1, 20), hist, res, pause=0, log=lambda *_: None)
    assert c2["updated"] == 1 and c2["fetched"] == 0
    assert hist.calls[-1][0] == date(2020, 1, 11)     # tail only — not 2020-01-01

    # 3) cached and up to date -> skipped, NO fetch at all
    hist.calls.clear()
    c3 = hh.run_harvest_history(["X"], date(2020, 1, 1), date(2020, 1, 20), hist, res, pause=0, log=lambda *_: None)
    assert c3["skipped"] == 1 and hist.calls == []
