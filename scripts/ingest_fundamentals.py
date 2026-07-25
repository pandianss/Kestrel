"""Ingest company results as filed → point-in-time fundamentals store.

Polls a FilingsSource for results filed since the last run, parses each XBRL,
and appends a point-in-time FundamentalRecord (dated by filing date) to the
store. Idempotent — re-running re-ingests nothing already recorded.

    python scripts/ingest_fundamentals.py           # dev source (runs today)

⚠️ The real NSE feed (NSEFilingsSource) needs live headers/cookies and its
XBRL→field mapping must be calibrated against real filings on-host (filings.py).
Until then this runs the StaticFilings dev source so the store + quality/value
factors are exercisable end-to-end. When a filing lands, the dashboard's
"fundamentals" recommendation self-clears.
"""
from __future__ import annotations

import sys
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kestrel.data.filings import FiledResult, FilingsSource, StaticFilings, to_record
from kestrel.data.fundamentals_store import FundamentalsConflictError, FundamentalsStore

STORE_ROOT = "data/fundamentals"          # the real store (a real feed writes here)
DEV_STORE_ROOT = "data/_dev_fundamentals"  # dev smoke test — kept out of the real store

# A tiny dev filing so the pipeline runs before the NSE feed is calibrated.
_DEV_XBRL = (
    b'<xbrl><RevenueFromOperations contextRef="Q" unitRef="INR">1000000</RevenueFromOperations>'
    b'<ProfitLossForPeriod contextRef="Q" unitRef="INR">120000</ProfitLossForPeriod>'
    b'<BasicEarningsPerShare contextRef="Q" unitRef="INR/sh">12.0</BasicEarningsPerShare></xbrl>'
)
DEV_SOURCE = StaticFilings([
    (FiledResult("DEVCO", date(2026, 3, 31), date(2026, 5, 14)), _DEV_XBRL),
])


def ingest(source: FilingsSource, store: FundamentalsStore, since: date) -> int:
    """Fetch, parse, and store filings since `since`. Returns count written."""
    from kestrel.data.filings import extract_financials

    written = 0
    for filed in source.recent(since):
        fin = extract_financials(source.fetch_xbrl(filed))
        eps = fin.get("basic_eps")
        if eps is None:
            print(f"  skip {filed.symbol} {filed.period_end}: no EPS parsed")
            continue
        # book value / ROE need more fields than a results XBRL always carries;
        # left None here until the tag map is calibrated on-host.
        rec = to_record(filed, eps_ttm=float(eps), book_value_per_share=0.0)
        try:
            if store.add(rec):
                written += 1
                print(f"  + {filed.symbol} {filed.period_end} (filed {filed.filing_date}) EPS {eps}")
        except FundamentalsConflictError as e:
            print(f"  CONFLICT (not overwritten): {e}")
    return written


def main() -> None:
    # Dev smoke test writes to a SEPARATE store so it never pollutes the real
    # one (which would falsely clear the dashboard's fundamentals rec). The real
    # NSE ingestion, once calibrated, targets STORE_ROOT = data/fundamentals.
    store = FundamentalsStore(DEV_STORE_ROOT)
    print("Ingesting filed results — DEV smoke test (NSE feed pending calibration)")
    print(f"  (writing to {DEV_STORE_ROOT}, not the real {STORE_ROOT})")
    n = ingest(DEV_SOURCE, store, date(2000, 1, 1))
    print(f"  wrote {n} new record(s); dev store holds {len(store.symbols())} symbol(s).")


if __name__ == "__main__":
    main()
