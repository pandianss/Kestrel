"""Reference-data sources for the daily snapshotter.

A `ReferenceSource` fetches *today's* reference dataset (instruments master,
ban list, circuit limits) as raw bytes. The snapshotter archives whatever it
returns immutably (`SnapshotStore`); the source is a thin, swappable adapter.

Two implementations:

  * `KiteInstrumentsSource` — the real one. GETs Kite's instruments CSV (doc
    02 §4), which the endpoint already returns as CSV, so it is archived
    verbatim. Needs a valid access_token (mint it with scripts/kite_login.py);
    without one it fails loudly rather than returning stale or partial data.
    Build it from the token store with `from_token_store`.

  * `StaticListSource` — a development source that emits a minimal instruments
    CSV from a Python list, so the snapshot → point-in-time-universe → backtest
    loop is exercisable *today*, before Kite auth exists.
"""
from __future__ import annotations

import io
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class ReferenceSource(Protocol):
    #: dataset name under which the snapshotter files this source's output.
    dataset: str
    #: file extension for the archived bytes.
    ext: str
    #: human-readable provenance string, recorded in the manifest.
    source_id: str

    def fetch(self) -> bytes:
        """Return today's reference dataset as raw bytes, or raise. Must never
        return stale or partial data silently — a bad fetch is an exception."""
        ...


_KITE_INSTRUMENTS_URL = "https://api.kite.trade/instruments"
_KITE_API_VERSION = "3"


class KiteInstrumentsSource:
    """Kite's daily instruments master (doc 02 §4): a CSV of all tradable
    instruments, regenerated ~08:30 IST daily. Fields include instrument_token,
    exchange_token, tradingsymbol, name, expiry, strike, tick_size, lot_size,
    instrument_type, segment, exchange.

    The endpoint returns CSV directly, so it is archived verbatim — the stored
    form is the raw exchange dataset, not a re-serialised copy. Needs a valid
    access_token; build it from the token store with `from_token_store`. The
    one network call is behind an injectable `http` so it is testable offline.
    """

    dataset = "instruments"
    ext = "csv"
    source_id = "kite:/instruments"

    def __init__(
        self,
        api_key: str,
        access_token: str,
        *,
        http: "Callable[[str, dict], bytes] | None" = None,
    ):
        if not api_key or not access_token:
            raise ValueError(
                "KiteInstrumentsSource needs api_key and a live access_token. "
                "Mint one with scripts/kite_login.py (doc 10 §2), then use "
                "from_token_store(). Use StaticListSource for development."
            )
        self._api_key = api_key
        self._access_token = access_token
        self._http = http or _default_get

    @classmethod
    def from_token_store(cls, store, *, now: datetime, http=None) -> "KiteInstrumentsSource":
        """Build from a valid stored token, or raise with a clear pointer to
        the login step. `now` decides validity (06:00-IST expiry)."""
        token = store.load_valid(now)
        if token is None:
            raise RuntimeError(
                "no valid Kite token in the store — run scripts/kite_login.py "
                "first (the token expires at 06:00 IST daily; doc 10 §2)."
            )
        return cls(token.api_key, token.access_token, http=http)

    def fetch(self) -> bytes:
        headers = {
            "X-Kite-Version": _KITE_API_VERSION,
            "Authorization": f"token {self._api_key}:{self._access_token}",
        }
        try:
            raw = self._http(_KITE_INSTRUMENTS_URL, headers)
        except urllib.error.HTTPError as e:
            # 403 here means the token expired/was rejected — a real, actionable
            # cause, distinct from an empty dump.
            raise RuntimeError(
                f"Kite instruments fetch rejected (HTTP {e.code}) — token likely "
                f"expired; re-run scripts/kite_login.py."
            ) from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"could not reach Kite instruments endpoint: {e.reason}") from None
        if not raw or raw.count(b"\n") < 2:
            raise RuntimeError(
                "Kite returned an empty/degenerate instruments dump — refusing to "
                "snapshot it (D-15: never archive empty reference data over nothing)."
            )
        return raw


def _default_get(url: str, headers: dict) -> bytes:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed host)
        return resp.read()


class StaticListSource:
    """Development source: a minimal instruments CSV from a symbol list, so the
    archival + point-in-time flow runs before Kite auth exists. Marks itself as
    a dev source in provenance so a snapshot taken from it is never mistaken for
    the real thing."""

    dataset = "instruments"
    ext = "csv"

    def __init__(self, symbols: list[str], exchange: str = "NSE"):
        self._symbols = list(symbols)
        self._exchange = exchange
        self.source_id = f"dev:static_list[{len(symbols)}@{exchange}]"

    def fetch(self) -> bytes:
        import csv

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["tradingsymbol", "exchange", "instrument_type", "segment"])
        for s in self._symbols:
            writer.writerow([s, self._exchange, "EQ", f"{self._exchange}"])
        return buf.getvalue().encode("utf-8")
