"""Reference-data sources for the daily snapshotter.

A `ReferenceSource` fetches *today's* reference dataset (instruments master,
ban list, circuit limits) as raw bytes. The snapshotter archives whatever it
returns immutably (`SnapshotStore`); the source is a thin, swappable adapter.

Two implementations:

  * `KiteInstrumentsSource` — the real one. Fetches Kite's gzipped instruments
    CSV (doc 02 §4). Structured and ready, but **inert until an access token is
    supplied** — the data plane needs no static IP, but the instruments dump
    still requires an authenticated session. It fails loudly rather than
    returning stale or partial data.

  * `StaticListSource` — a development source that emits a minimal instruments
    CSV from a Python list, so the snapshot → point-in-time-universe → backtest
    loop is exercisable *today*, before Kite auth exists.
"""
from __future__ import annotations

import io
from typing import Protocol, runtime_checkable


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


class KiteInstrumentsSource:
    """Kite's daily instruments master (doc 02 §4): gzipped CSV of all
    tradable instruments, regenerated ~08:30 daily. Fields include
    instrument_token, exchange_token, tradingsymbol, name, expiry, strike,
    tick_size, lot_size, instrument_type, segment, exchange.

    ⚠️ Requires an authenticated Kite session (access_token). Left inert here
    on purpose — wiring the real HTTP call belongs with the Phase-0 auth
    helper (doc 10 §2), and doing it without a token would only produce a
    misleading failure. The class exists so the snapshotter is complete and the
    integration point is unambiguous.
    """

    dataset = "instruments"
    ext = "csv"
    source_id = "kite:/instruments"

    def __init__(self, kite_client=None):
        self._kite = kite_client

    def fetch(self) -> bytes:
        if self._kite is None:
            raise RuntimeError(
                "KiteInstrumentsSource needs an authenticated Kite client "
                "(access_token). See doc 10 §2 (daily login) — the instruments "
                "dump is not available unauthenticated. Use StaticListSource for "
                "development until auth is wired."
            )
        # Real call (once a client exists): the pykiteconnect `instruments()`
        # returns parsed rows; we re-serialise to CSV bytes for archival so the
        # stored form is the raw dataset, not a Python object.
        rows = self._kite.instruments()  # list[dict]
        if not rows:
            raise RuntimeError("Kite returned an empty instruments dump — refusing "
                               "to snapshot empty reference data (D-15).")
        import csv

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue().encode("utf-8")


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
