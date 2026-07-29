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


def backfill_symbol(source, store, symbol, *, pause=0.3, sleep=time.sleep, log=print,
                    archive=None) -> dict:
    """Fetch `symbol`'s full history and store one record per quarter, preferring
    consolidated. The raw XBRL of EVERY filing is archived (D-15) — archival is
    NOT gated on ingestion, so even a quarter whose derived record already exists
    still has its original saved (closes the pre-archive gap). Resumable: once a
    filing is archived, get_xbrl reads it locally (no re-fetch); ingestion of a
    quarter already stored is skipped."""
    from kestrel.data.filing_archive import FilingArchive, get_xbrl
    if archive is None:
        archive = FilingArchive()
    filings = source.recent(date(2000, 1, 1), symbol=symbol)
    # best (highest-basis) EPS per new period_end
    best: dict[date, tuple] = {}
    fetched = 0
    for filed in filings:
        have_period = store.has_period(symbol, filed.period_end)
        from_archive = False
        try:
            # Always archive the original, even for an already-ingested quarter:
            # the record may have been stored by a pre-archive run that discarded
            # the source doc. has_period gates INGESTION, not archival.
            xb, from_archive = get_xbrl(archive, source, symbol, filed)
            fetched += 0 if from_archive else 1
            if not have_period:
                fin = current_period_financials(xb)   # P&L + balance sheet
                if fin.get("basic_eps") is not None:
                    rank = _BASIS_RANK.get(report_basis(xb), 0)
                    cur = best.get(filed.period_end)
                    if cur is None or rank > cur[0]:
                        best[filed.period_end] = (rank, fin, filed.filing_date)
        except Exception:  # noqa: BLE001 — ambiguous/parse/network; skip one filing
            pass
        if not from_archive:
            sleep(pause)   # pace only real network fetches; archive reads are free

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


DONE_FILE = Path(STORE_ROOT) / "_backfilled.txt"


def _load_done() -> set[str]:
    return set(DONE_FILE.read_text(encoding="utf-8").split()) if DONE_FILE.exists() else set()


def _mark_done(sym: str) -> None:
    DONE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DONE_FILE.open("a", encoding="utf-8") as f:
        f.write(sym + "\n")


def _symbols_from_args() -> list[str]:
    if "--all" in sys.argv:
        return FundamentalsStore(STORE_ROOT).symbols()
    if "--nifty50" in sys.argv:
        from kestrel.data.constituents import NSEConstituentsSource, parse_symbols
        return parse_symbols(NSEConstituentsSource("nifty50").fetch())
    return [a for a in sys.argv[1:] if not a.startswith("--")]


def main() -> int:
    symbols = _symbols_from_args()
    if not symbols:
        print("Usage: python scripts/backfill_fundamentals.py SYMBOL [...] | --nifty50 | --all")
        return 2
    getter = make_nse_getter()
    from kestrel.data.filings import NSEFilingsSource
    src = NSEFilingsSource(http=getter)
    store = FundamentalsStore(STORE_ROOT)

    # Symbol-level resumability: skip companies already backfilled (survives a
    # stop/restart of this multi-hour batch without re-fetching their history).
    done = _load_done()
    pending = [s for s in symbols if s not in done]
    print("=================================================================")
    print("  KESTREL FUNDAMENTALS HISTORY BACKFILL")
    print("=================================================================")
    print(f"  {len(symbols)} symbol(s); {len(done)} already done; {len(pending)} to go.")
    print(f"  Each pulls a company's full quarterly results history from NSE.")
    print(f"  Resumable — safe to stop (Ctrl-C) and restart; it skips done names.")
    print("=================================================================")

    total = 0
    t0 = time.perf_counter()
    for i, sym in enumerate(pending, 1):
        try:
            total += backfill_symbol(src, store, sym)["written"]
            _mark_done(sym)
        except Exception as e:  # noqa: BLE001 — one symbol shouldn't kill the batch
            print(f"  [ERROR] {sym}: {e}")
        if i % 25 == 0 or i == len(pending):
            rate = i / max(time.perf_counter() - t0, 1e-6)
            eta = (len(pending) - i) / rate / 60.0
            print(f"  … {i}/{len(pending)} done  (+{total} quarters)  ~{eta:.0f} min left")

    print(f"\nDone. +{total} quarter-record(s) across {len(pending)} symbol(s). "
          f"Run scripts/fundamentals_trends.py to compare.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
