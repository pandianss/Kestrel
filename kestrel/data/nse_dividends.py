"""NSE dividend feed (G-08) — the source that drives dividend adjustment.

Kite adjusts historical candles for splits/bonuses but not dividends, so every
ex-dividend date is an artificial gap-down (doc 11 G-08). `corporate_actions.py`
has the back-adjustment math and the `DividendSource` seam; this is the real
source behind that seam — NSE's public corporate-actions feed.

`NSEDividendSource.events(symbol)` returns cash-dividend `DividendEvent`s parsed
from subjects like "Dividend - Rs 6 Per Share" (interim/final/special all count;
bonuses and splits are Kite's job and are ignored here). Feed the result to
`adjust_for_dividends` to put a Kite price series on a total-return basis.

`http` is injectable for tests; the real getter is NSE's session getter.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from kestrel.data.corporate_actions import DividendEvent
from kestrel.data.nse_http import nse_date

_URL = ("https://www.nseindia.com/api/corporates-corporateActions"
        "?index=equities&symbol={symbol}")
#: "Dividend - Rs 6 Per Share", "Interim Dividend Rs. 5.50 Per Share", …
_AMOUNT = re.compile(r"Rs\.?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


def parse_dividend_events(symbol: str, rows: list[dict]) -> list[DividendEvent]:
    """Cash-dividend events from NSE corporate-action rows. Rows whose subject
    is not a dividend, or from which no 'Rs X' amount can be read, are skipped."""
    out: list[DividendEvent] = []
    for r in rows:
        subject = str(r.get("subject", ""))
        if "dividend" not in subject.lower():
            continue    # bonuses / splits handled by Kite, not here
        m = _AMOUNT.search(subject)
        ex = r.get("exDate") or r.get("exdate")
        if not m or not ex:
            continue
        try:
            exd = nse_date(ex)
        except ValueError:
            continue
        out.append(DividendEvent(symbol, exd, float(m.group(1))))
    return out


class NSEDividendSource:
    """Fetches and parses NSE cash dividends for a symbol. Implements the
    `DividendSource` protocol (`events`)."""

    def __init__(self, *, http: Callable[[str], bytes] | None = None):
        self._http = http

    def events(self, symbol: str) -> list[DividendEvent]:
        if self._http is None:
            from kestrel.data.nse_http import make_nse_getter
            self._http = make_nse_getter(
                seed_url="https://www.nseindia.com/companies-listing/corporate-filings-actions")
        raw = self._http(_URL.format(symbol=symbol))
        data = json.loads(raw)
        rows = data if isinstance(data, list) else data.get("data", [])
        return parse_dividend_events(symbol, rows)
