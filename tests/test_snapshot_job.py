"""Tests for the daily snapshot job's source selection — specifically the
require-live invariant that stops a scheduler from archiving dev data as if it
were a real trading-day snapshot (the whole reason the scheduler is safe to
automate).
"""
import importlib
from datetime import datetime, timezone

import pytest

# Import the script module by path-independent name.
snap_job = importlib.import_module("scripts.snapshot_reference")
from kestrel.data.reference import KiteInstrumentsSource, StaticListSource
from kestrel.kite.auth import IST, exchange_request_token
from kestrel.kite.tokenstore import FileTokenStore


def _fake_http_ok(url, data, headers):
    import json
    return json.dumps({"data": {"access_token": "TOK", "user_id": "U1"}}).encode()


def test_require_live_raises_without_token(tmp_path, monkeypatch):
    monkeypatch.setattr(snap_job, "TOKEN_PATH", str(tmp_path / "absent.json"))
    now = datetime(2026, 7, 23, 4, 0, tzinfo=timezone.utc)
    with pytest.raises(snap_job.NoLiveTokenError):
        snap_job.choose_source(now, require_live=True)


def test_non_strict_falls_back_to_dev(tmp_path, monkeypatch):
    monkeypatch.setattr(snap_job, "TOKEN_PATH", str(tmp_path / "absent.json"))
    now = datetime(2026, 7, 23, 4, 0, tzinfo=timezone.utc)
    src = snap_job.choose_source(now, require_live=False)
    assert isinstance(src, StaticListSource)


def test_uses_live_source_when_token_present(tmp_path, monkeypatch):
    token_path = tmp_path / "kite_token.json"
    monkeypatch.setattr(snap_job, "TOKEN_PATH", str(token_path))
    mint = _ist(2026, 7, 23, 8, 30)
    tok = exchange_request_token("KEY", "SECRET", "req", now=mint, http=_fake_http_ok)
    FileTokenStore(token_path).save(tok)

    src = snap_job.choose_source(mint, require_live=True)
    assert isinstance(src, KiteInstrumentsSource)


def test_main_returns_3_without_token(tmp_path, monkeypatch):
    """End-to-end: strict main() returns 3 and touches no store."""
    monkeypatch.setattr(snap_job, "TOKEN_PATH", str(tmp_path / "absent.json"))
    monkeypatch.setattr(snap_job, "STORE_ROOT", str(tmp_path / "snapshots"))
    rc = snap_job.main(["--require-live"])
    assert rc == 3
    assert not (tmp_path / "snapshots").exists()   # nothing written


def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST).astimezone(timezone.utc)
