"""Kite historical price loader — real Indian daily bars for backtests.

With a live token, Kite's historical API serves daily candles back to 2012.
This replaces the Yahoo dev loader with real prices, volumes, and — through
the cost model — real costs. Two things it deliberately does not pretend to fix:

  * **Survivorship (G-43).** You can only query instrument tokens that still
    exist today, so a universe built from *today's* instruments master is still
    survivor-biased no matter how real the prices are. Real prices do not cure
    survivorship — the point-in-time universe does. This loader is for
    calibration and real-price factor runs, not for a trustworthy verdict on a
    survivor universe.

  * **Dividends (G-08).** Kite adjusts historical candles for splits and
    bonuses only — *not* dividends, rights, or demergers. Every ex-dividend
    date is a gap-down that was never a loss. A dividend-adjustment layer is a
    follow-up (flagged, not built here); until then, treat ex-div gaps as
    artefacts, not signal. Kite also rewrites candles in place on ex-dates
    (the D-15 twist), so a cached pull is an as-of snapshot — which is the
    behaviour we want, but it means a stale cache can disagree with a fresh one.

Design mirrors the rest of `data/`: token resolution comes from the captured
instruments snapshot, and the one network call is injectable so the parsing,
pagination, and rate-limit logic are tested offline with no live calls.
"""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Callable

import pandas as pd

_KITE_API_VERSION = "3"
_HIST_URL = "https://api.kite.trade/instruments/historical/{token}/{interval}"

# Kite's per-request candle-count ceiling, expressed as a day-span per interval.
# Daily allows a long window; we page conservatively under the documented cap.
_MAX_DAYS = {"day": 2000, "60minute": 400, "minute": 60}


class InstrumentResolver:
    """Maps a trading symbol to its Kite `instrument_token`, from an instruments
    master CSV. Built from the captured snapshot so resolution is point-in-time
    consistent with the data being analysed."""

    def __init__(self, rows: list[dict]):
        # index by (exchange, tradingsymbol) -> token, keeping EQ where ambiguous
        self._by_key: dict[tuple[str, str], int] = {}
        for r in rows:
            sym = r.get("tradingsymbol")
            exch = r.get("exchange")
            if not sym or not exch:
                continue
            token = r.get("instrument_token")
            if token in (None, ""):
                continue
            self._by_key[(exch, sym)] = int(token)

    @classmethod
    def from_csv_bytes(cls, content: bytes) -> "InstrumentResolver":
        return cls(list(csv.DictReader(io.StringIO(content.decode("utf-8")))))

    @classmethod
    def from_snapshot_store(cls, store, d: date, *, dataset: str = "instruments") -> "InstrumentResolver":
        content = store.asof(dataset, d)
        if content is None:
            raise RuntimeError(
                f"no instruments snapshot on/before {d} — run the snapshot job "
                f"first (scripts/snapshot_reference.py --require-live)."
            )
        return cls.from_csv_bytes(content)

    def token(self, symbol: str, *, exchange: str = "NSE") -> int:
        key = (exchange, symbol)
        if key not in self._by_key:
            raise KeyError(f"no instrument_token for {symbol} on {exchange}")
        return self._by_key[key]


def _default_get(url: str, headers: dict) -> bytes:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed host)
        return resp.read()


class KiteHistory:
    """Fetches daily OHLCV candles for an instrument token."""

    def __init__(
        self,
        api_key: str,
        access_token: str,
        *,
        http: Callable[[str, dict], bytes] | None = None,
        pause: float = 0.34,     # ~3 req/s, Kite historical rate limit
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not api_key or not access_token:
            raise ValueError("KiteHistory needs api_key and a live access_token")
        self._api_key = api_key
        self._access_token = access_token
        self._http = http or _default_get
        self._pause = pause
        self._sleep = sleep

    @classmethod
    def from_token_store(cls, store, *, now, http=None, **kw) -> "KiteHistory":
        token = store.load_valid(now)
        if token is None:
            raise RuntimeError(
                "no valid Kite token — run scripts/kite_login.py first "
                "(the token expires at 06:00 IST daily)."
            )
        return cls(token.api_key, token.access_token, http=http, **kw)

    def _headers(self) -> dict:
        return {
            "X-Kite-Version": _KITE_API_VERSION,
            "Authorization": f"token {self._api_key}:{self._access_token}",
        }

    def _windows(self, frm: date, to: date, interval: str) -> list[tuple[date, date]]:
        span = _MAX_DAYS.get(interval, 2000)
        out: list[tuple[date, date]] = []
        start = frm
        while start <= to:
            end = min(start + timedelta(days=span - 1), to)
            out.append((start, end))
            start = end + timedelta(days=1)
        return out

    def fetch_candles(
        self, instrument_token: int, frm: date, to: date, *, interval: str = "day"
    ) -> pd.DataFrame:
        """Daily OHLCV for one instrument over [frm, to], paginated under Kite's
        per-request window and paced for the rate limit. Returns a date-indexed
        frame with columns open/high/low/close/volume. Empty frame if no data."""
        frames: list[pd.DataFrame] = []
        windows = self._windows(frm, to, interval)
        for i, (w0, w1) in enumerate(windows):
            url = _HIST_URL.format(token=instrument_token, interval=interval) + "?" + urllib.parse.urlencode(
                {"from": w0.isoformat(), "to": w1.isoformat()}
            )
            try:
                raw = self._http(url, self._headers())
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    raise RuntimeError(
                        "Kite historical fetch rejected (403) — token likely "
                        "expired; re-run scripts/kite_login.py."
                    ) from None
                raise RuntimeError(f"Kite historical fetch failed (HTTP {e.code})") from None
            frames.append(_parse_candles(raw))
            if i < len(windows) - 1:
                self._sleep(self._pause)
        if not frames:
            return _empty_ohlcv()
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df


def _parse_candles(raw: bytes) -> pd.DataFrame:
    payload = json.loads(raw)
    candles = (payload.get("data") or {}).get("candles") or []
    if not candles:
        return _empty_ohlcv()
    idx, rows = [], []
    for c in candles:
        # [timestamp, open, high, low, close, volume, (oi?)]
        idx.append(pd.Timestamp(str(c[0])[:10]))
        rows.append((float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])))
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"])


def _empty_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
