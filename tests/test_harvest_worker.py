"""Tests for the reusable harvest and the background worker's lock/status.

All offline — no live NSE calls (the worker's _cycle uses the real source, but
its harvest logic, resumability, stop, lock, and status are tested here)."""
import json
import os
from datetime import date

from kestrel.data.filings import FiledResult, StaticFilings
from kestrel.data.fundamentals_store import FundamentalsStore
from scripts.harvest_fundamentals import run_harvest

_TAG = "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations"


def _xbrl(eps: float) -> bytes:
    return f'<xbrl><{_TAG} contextRef="OneD">{eps}</{_TAG}></xbrl>'.encode()


def _source():
    return StaticFilings([
        (FiledResult("AAA", date(2024, 3, 31), date(2024, 5, 15)), _xbrl(9.0)),
        (FiledResult("BBB", date(2024, 3, 31), date(2024, 5, 16)), _xbrl(4.0)),
    ])


def test_run_harvest_writes_new_then_skips_on_rerun(tmp_path):
    store = FundamentalsStore(tmp_path)
    c1 = run_harvest(_source(), store, date(2000, 1, 1), pause=0, sleep=lambda s: None)
    assert c1["written"] == 2 and c1["skipped"] == 0
    assert store.asof("AAA", date(2024, 12, 1)).eps_ttm == 9.0
    # resumable: a second run re-fetches nothing new
    c2 = run_harvest(_source(), store, date(2000, 1, 1), pause=0, sleep=lambda s: None)
    assert c2["written"] == 0 and c2["skipped"] == 2


def test_run_harvest_stops_when_asked(tmp_path):
    store = FundamentalsStore(tmp_path)
    c = run_harvest(_source(), store, date(2000, 1, 1), pause=0, sleep=lambda s: None,
                    should_stop=lambda: True)   # stop before the first filing
    assert c["written"] == 0


def test_worker_lock_prevents_double_run(tmp_path, monkeypatch):
    import scripts.harvest_worker as w
    real_pid = os.getpid()                       # this process is alive
    monkeypatch.setattr(w, "PIDFILE", tmp_path / "worker.pid")
    (tmp_path / "worker.pid").write_text(str(real_pid))   # "another" live worker
    monkeypatch.setattr(w.os, "getpid", lambda: real_pid + 1)   # we are a different pid
    assert w._acquire_lock() is False            # the alive pid in the file isn't us


def test_worker_lock_acquired_when_free(tmp_path, monkeypatch):
    import scripts.harvest_worker as w
    monkeypatch.setattr(w, "PIDFILE", tmp_path / "worker.pid")
    assert w._acquire_lock() is True             # no existing lock
    assert (tmp_path / "worker.pid").read_text().strip() == str(os.getpid())


def test_worker_status_written(tmp_path, monkeypatch):
    import scripts.harvest_worker as w
    monkeypatch.setattr(w, "STATUS", tmp_path / "status.json")
    w._write_status({"written": 3, "skipped": 5, "errors": 0}, symbols=8)
    data = json.loads((tmp_path / "status.json").read_text())
    assert data["written"] == 3 and data["symbols"] == 8 and "last_cycle" in data
