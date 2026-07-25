"""Full fundamentals harvest — ingest every available NSE results filing.

Batch version of scripts/ingest_fundamentals.py against the live feed. Fetches
the corporate-results list, then pulls + parses each XBRL into a point-in-time
record (current-quarter, `OneD`). Rate-limited and **resumable**: the store
skips filings it already has without re-fetching, so re-running after an
interruption is cheap and safe.

    python scripts/harvest_fundamentals.py                 # everything available
    python scripts/harvest_fundamentals.py --limit 25      # a capped batch (proof)
    python scripts/harvest_fundamentals.py --since 2025-01-01

Writes to the REAL store (data/fundamentals). Public NSE data — no Kite token.
Note: a results XBRL gives EPS/revenue/PAT but not net worth, so records carry
EPS (feeds value/earnings); ROE-based quality needs balance-sheet data (later).
"""
from __future__ import annotations

import sys
import time
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kestrel.data.filings import (
    AmbiguousContextError,
    NSEFilingsSource,
    current_quarter_financials,
    to_record,
)
from kestrel.data.fundamentals_store import FundamentalsConflictError, FundamentalsStore
from kestrel.data.nse_http import make_nse_getter

STORE_ROOT = "data/fundamentals"


def _arg(flag: str, default: str | None = None) -> str | None:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main() -> int:
    limit = int(_arg("--limit", "0") or 0)
    since = date.fromisoformat(_arg("--since", "2000-01-01"))
    pause = float(_arg("--pause", "0.3"))

    getter = make_nse_getter()
    src = NSEFilingsSource(http=getter)
    store = FundamentalsStore(STORE_ROOT)

    print(f"Harvesting NSE results filings since {since}"
          + (f" (limit {limit})" if limit else "") + " ...")
    filings = src.recent(since)
    if limit:
        filings = filings[:limit]
    print(f"  {len(filings)} filing(s) to consider")

    written = skipped = no_eps = ambiguous = errors = 0
    for i, filed in enumerate(filings, 1):
        if store.has(filed.symbol, filed.period_end, filed.filing_date):
            skipped += 1
            continue
        try:
            fin = current_quarter_financials(src.fetch_xbrl(filed))
            eps = fin.get("basic_eps")
            if eps is None:
                no_eps += 1
                continue
            if store.add(to_record(filed, eps_ttm=float(eps), book_value_per_share=0.0)):
                written += 1
        except AmbiguousContextError:
            ambiguous += 1
        except FundamentalsConflictError:
            errors += 1
        except Exception:  # noqa: BLE001 — one bad filing shouldn't stop the harvest
            errors += 1
        time.sleep(pause)
        if i % 50 == 0:
            print(f"  … {i}/{len(filings)}  (written {written}, skipped {skipped})")

    print(f"\nDone. written {written}, already-had {skipped}, no-EPS {no_eps}, "
          f"ambiguous {ambiguous}, errors {errors}.")
    print(f"Store now holds {len(store.symbols())} symbol(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
