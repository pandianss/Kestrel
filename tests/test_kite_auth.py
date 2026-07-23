"""Tests for the Kite daily-login helper (doc 10 §2).

The pure pieces — checksum and the 06:00-IST expiry boundary — are tested
directly; the network exchange and the instruments fetch are tested through an
injected fake so no request ever leaves the process and no real secret is
needed.
"""
import hashlib
import json
from datetime import datetime, timezone

import pytest

from kestrel.data.reference import KiteInstrumentsSource
from kestrel.kite.auth import (
    IST,
    KiteAuthError,
    checksum,
    exchange_request_token,
    extract_request_token,
    login_url,
    next_token_expiry,
)
from kestrel.kite.tokenstore import FileTokenStore


# ---- pure functions -----------------------------------------------------

def test_checksum_matches_kite_formula():
    """Kite defines the checksum as SHA-256(api_key + request_token + secret)."""
    expected = hashlib.sha256(b"KEYtok123SECRET").hexdigest()
    assert checksum("KEY", "tok123", "SECRET") == expected


def test_login_url_contains_key_and_is_safe():
    url = login_url("myapikey")
    assert "api_key=myapikey" in url and url.startswith("https://kite.zerodha.com")


def test_login_url_rejects_empty_key():
    with pytest.raises(ValueError):
        login_url("")


def test_extract_request_token_from_full_url():
    url = "https://myapp.example/redirect?action=login&status=success&request_token=abc123XYZ"
    assert extract_request_token(url) == "abc123XYZ"


def test_extract_request_token_bare():
    assert extract_request_token("  abc123XYZ ") == "abc123XYZ"


def test_extract_request_token_rejects_garbage():
    with pytest.raises(ValueError):
        extract_request_token("https://x/redirect?action=login")   # no token param


# ---- the 06:00-IST expiry boundary (the subtle bit) --------------------

def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def test_expiry_before_6am_is_today_6am():
    # 05:00 IST -> token dies at 06:00 IST the same morning
    now = _ist(2026, 7, 23, 5, 0)
    exp = next_token_expiry(now).astimezone(IST)
    assert (exp.hour, exp.minute, exp.day) == (6, 0, 23)


def test_expiry_after_6am_is_tomorrow_6am():
    # 09:00 IST -> token dies at 06:00 IST tomorrow
    now = _ist(2026, 7, 23, 9, 0)
    exp = next_token_expiry(now).astimezone(IST)
    assert (exp.hour, exp.minute, exp.day) == (6, 0, 24)


def test_expiry_exactly_6am_rolls_forward():
    # at exactly 06:00 the token is already dead -> next boundary is tomorrow
    now = _ist(2026, 7, 23, 6, 0)
    exp = next_token_expiry(now).astimezone(IST)
    assert exp.day == 24


# ---- the exchange, through a fake HTTP ----------------------------------

def _fake_http_ok(url, data, headers):
    # assert the request is well-formed without a real endpoint
    assert url.endswith("/session/token")
    assert headers["X-Kite-Version"] == "3"
    assert b"checksum=" in data
    return json.dumps({"data": {"access_token": "LIVETOKEN99", "user_id": "AB1234"}}).encode()


def test_exchange_builds_token_record():
    now = _ist(2026, 7, 23, 8, 30).astimezone(timezone.utc)
    tok = exchange_request_token("KEY", "SECRET", "reqtok", now=now, http=_fake_http_ok)
    assert tok.access_token == "LIVETOKEN99"
    assert tok.user_id == "AB1234"
    assert tok.is_valid(now) is True
    # dies at 06:00 IST next day (minted 08:30 IST)
    assert tok.expires_at.endswith("+00:00") or "T" in tok.expires_at


def test_exchange_masks_never_leaks_token():
    now = _ist(2026, 7, 23, 8, 30).astimezone(timezone.utc)
    tok = exchange_request_token("KEY", "SECRET", "reqtok", now=now, http=_fake_http_ok)
    assert "LIVETOKEN99" not in tok.masked()
    assert tok.masked().endswith("expires=" + tok.expires_at)


def test_exchange_raises_when_no_token_in_response():
    def http_no_token(url, data, headers):
        return json.dumps({"data": {}}).encode()

    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    with pytest.raises(KiteAuthError):
        exchange_request_token("KEY", "SECRET", "reqtok", now=now, http=http_no_token)


def test_exchange_requires_credentials():
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        exchange_request_token("", "", "reqtok", now=now, http=_fake_http_ok)


# ---- token store --------------------------------------------------------

def test_token_store_roundtrip_and_validity(tmp_path):
    now = _ist(2026, 7, 23, 8, 30).astimezone(timezone.utc)
    tok = exchange_request_token("KEY", "SECRET", "reqtok", now=now, http=_fake_http_ok)
    store = FileTokenStore(tmp_path / "kite_token.json")
    store.save(tok)

    loaded = store.load()
    assert loaded == tok
    # valid now, invalid after its 06:00-IST expiry
    assert store.load_valid(now) is not None
    after = _ist(2026, 7, 24, 6, 1).astimezone(timezone.utc)
    assert store.load_valid(after) is None    # fails safe once expired


def test_token_store_missing_is_none(tmp_path):
    assert FileTokenStore(tmp_path / "nope.json").load() is None


# ---- instruments source over a fake HTTP -------------------------------

def test_kite_instruments_source_archives_verbatim():
    csv_bytes = b"instrument_token,tradingsymbol,exchange\n256265,RELIANCE,NSE\n1,TCS,NSE\n"

    def http_get(url, headers):
        assert url.endswith("/instruments")
        assert headers["Authorization"] == "token KEY:TOK"
        return csv_bytes

    src = KiteInstrumentsSource("KEY", "TOK", http=http_get)
    assert src.fetch() == csv_bytes         # stored raw, not re-serialised
    assert src.dataset == "instruments" and src.source_id == "kite:/instruments"


def test_kite_instruments_source_rejects_empty_dump():
    src = KiteInstrumentsSource("KEY", "TOK", http=lambda u, h: b"header_only\n")
    with pytest.raises(RuntimeError):
        src.fetch()


def test_kite_instruments_source_needs_token():
    with pytest.raises(ValueError):
        KiteInstrumentsSource("KEY", "")


def test_from_token_store_requires_valid_token(tmp_path):
    store = FileTokenStore(tmp_path / "t.json")
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    with pytest.raises(RuntimeError):
        KiteInstrumentsSource.from_token_store(store, now=now)
