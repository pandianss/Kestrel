"""Index constituents → a clean stock universe (fixes the ETF/bond problem).

The instruments-master EQ filter yields ~9.8k cash-segment names including
bonds, ETFs, REITs and InvITs (doc 11). An index-constituents list — NSE's own
published NIFTY 50/100/200/500 membership — is a clean roster of *stocks*, and
snapshotting it daily (like the instruments master) builds point-in-time
membership going forward, which is what fixes survivorship (G-43).

  * `NSEConstituentsSource` fetches NSE's public index CSV. It plugs into the
    same `SnapshotStore` as the instruments snapshotter (dataset
    `constituents_<index>`), so the daily job is one line and D-15 immutability
    applies unchanged.

  * `build_index_universe` (in pit.py) reads those snapshots into a
    `PointInTimeUniverse` — the trustworthy stock universe for a factor test.

Historical membership before we started snapshotting is not free (NSE doesn't
publish it); that remains a vendor/deferred item. Forward from the first
snapshot, membership is captured and correct.
"""
from __future__ import annotations

import csv
import io
from typing import Callable

_BASE = "https://nsearchives.nseindia.com/content/indices/"
INDEX_CSV = {
    "nifty50": _BASE + "ind_nifty50list.csv",
    "nifty100": _BASE + "ind_nifty100list.csv",
    "nifty200": _BASE + "ind_nifty200list.csv",
    "nifty500": _BASE + "ind_nifty500list.csv",
    "niftytotalmarket": _BASE + "ind_niftytotalmarket_list.csv",
}

#: Series worth trading as equity. EQ = rolling settlement; BE = trade-to-trade
#: (still a stock, just tighter surveillance). Others (debt etc.) are excluded.
EQUITY_SERIES = {"EQ", "BE"}


def parse_symbols(csv_bytes: bytes, *, series: set[str] | None = EQUITY_SERIES) -> list[str]:
    """Symbols from an NSE index CSV (columns: Company Name, Industry, Symbol,
    Series, ISIN Code), optionally restricted to equity series."""
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    out = []
    for r in reader:
        sym = (r.get("Symbol") or "").strip()
        if not sym:
            continue
        if series is not None and (r.get("Series") or "EQ").strip() not in series:
            continue
        out.append(sym)
    return out


class NSEConstituentsSource:
    """Fetches one NSE index's constituents CSV. Shape matches the reference
    sources: (dataset, ext, source_id, fetch) so it snapshots like the rest.
    `http` is injectable for tests; the daily job passes a real NSE getter."""

    ext = "csv"

    def __init__(self, index: str = "nifty500", *, http: Callable[[str], bytes] | None = None):
        if index not in INDEX_CSV:
            raise ValueError(f"unknown index {index!r}; known: {sorted(INDEX_CSV)}")
        self.index = index
        self.dataset = f"constituents_{index}"
        self.source_id = f"nse:indices/{index}"
        self._http = http

    def fetch(self) -> bytes:
        if self._http is None:
            from kestrel.data.nse_http import make_nse_getter
            self._http = make_nse_getter()
        raw = self._http(INDEX_CSV[self.index])
        if b"Symbol" not in raw[:200]:
            raise RuntimeError(
                f"NSE constituents CSV for {self.index} did not look like the "
                f"expected format (no 'Symbol' header) — refusing to snapshot it."
            )
        return raw
