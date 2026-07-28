"""Backfill a company's fundamentals HISTORY (multiple quarters) for trend
analysis. NSE's per-symbol endpoint returns the full results history, so this
makes 'is performance improving or declining?' answerable today.

    python scripts/backfill_fundamentals.py RELIANCE INFY TCS
    python scripts/backfill_fundamentals.py --nifty50        # all NIFTY 50 names

A quarter is filed twice (standalone + consolidated); this prefers CONSOLIDATED
(the headline) and stores one record per quarter. Resumable: a quarter already
in the store is skipped without re-fetching. Public NSE data — no Kite token.
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kestrel.data.filings import build_record_from_financials, current_period_financials, report_basis
from kestrel.data.fundamentals_store import FundamentalsConflictError, FundamentalsStore
from kestrel.data.nse_http import make_nse_getter

STORE_ROOT = "data/fundamentals"
_BASIS_RANK = {"consolidated": 2, "standalone": 1, "unknown": 0}


def backfill_symbol(source, store, symbol, *, pause=0.3, sleep=time.sleep, log=print) -> dict:
    """Fetch `symbol`'s full history and store one record per quarter, preferring
    consolidated. Resumable: quarters already stored are skipped un-fetched."""
    filings = source.recent(date(2000, 1, 1), symbol=symbol)
    # best (highest-basis) EPS per new period_end
    best: dict[date, tuple] = {}
    fetched = 0
    for filed in filings:
        if store.has_period(symbol, filed.period_end):
            continue   # already have this quarter — don't re-fetch either filing
        try:
            xb = source.fetch_xbrl(filed)
            fetched += 1
            fin = current_period_financials(xb)   # P&L + balance sheet
            if fin.get("basic_eps") is None:
                continue
            rank = _BASIS_RANK.get(report_basis(xb), 0)
            cur = best.get(filed.period_end)
            if cur is None or rank > cur[0]:
                best[filed.period_end] = (rank, fin, filed.filing_date)
        except Exception:  # noqa: BLE001 — ambiguous/parse/network; skip one filing
            pass
        sleep(pause)

    written = 0
    for pe, (_rank, fin, fd) in best.items():
        from kestrel.data.filings import FiledResult
        try:
            if store.add(build_record_from_financials(FiledResult(symbol, pe, fd), fin)):
                written += 1
        except FundamentalsConflictError:
            pass
    log(f"  {symbol}: +{written} quarter(s) (fetched {fetched} filing(s)); "
        f"history now {len(store.records(symbol))}")
    return {"symbol": symbol, "written": written, "fetched": fetched}


def _symbols_from_args() -> list[str]:
    if "--nifty50" in sys.argv:
        from kestrel.data.constituents import NSEConstituentsSource, parse_symbols
        return parse_symbols(NSEConstituentsSource("nifty50").fetch())
    return [a for a in sys.argv[1:] if not a.startswith("--")]


def main() -> int:
    symbols = _symbols_from_args()
    if not symbols:
        print("Usage: python scripts/backfill_fundamentals.py SYMBOL [SYMBOL ...] | --nifty50")
        return 2
    getter = make_nse_getter()
    from kestrel.data.filings import NSEFilingsSource
    src = NSEFilingsSource(http=getter)
    store = FundamentalsStore(STORE_ROOT)
    print(f"Backfilling fundamentals history for {len(symbols)} symbol(s) ...")
    total = 0
    for sym in symbols:
        total += backfill_symbol(src, store, sym)["written"]
    print(f"\nDone. +{total} quarter-record(s). Run scripts/fundamentals_trends.py to compare.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
