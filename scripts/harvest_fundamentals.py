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


def run_harvest(source, store, since, *, limit=0, pause=0.3,
                sleep=time.sleep, log=print, should_stop=None) -> dict:
    """Ingest new filings from `source` into `store`. Resumable (skips filings
    already stored, never re-fetching them) and interruptible (`should_stop` is
    polled each iteration). Reused by the CLI and the background worker. Returns
    a counts dict."""
    filings = source.recent(since)
    if limit:
        filings = filings[:limit]
    log(f"  {len(filings)} filing(s) to consider")

    c = dict(written=0, skipped=0, no_eps=0, ambiguous=0, errors=0)
    for i, filed in enumerate(filings, 1):
        if should_stop is not None and should_stop():
            log("  stop requested — leaving the rest for the next cycle")
            break
        if store.has(filed.symbol, filed.period_end, filed.filing_date):
            c["skipped"] += 1
            continue
        try:
            fin = current_quarter_financials(source.fetch_xbrl(filed))
            eps = fin.get("basic_eps")
            if eps is None:
                c["no_eps"] += 1
            elif store.add(to_record(filed, eps_ttm=float(eps), book_value_per_share=0.0)):
                c["written"] += 1
        except AmbiguousContextError:
            c["ambiguous"] += 1
        except Exception:  # noqa: BLE001 — one bad filing shouldn't stop the harvest
            c["errors"] += 1
        sleep(pause)   # pace every network fetch; skips (has) never reach here
        if i % 50 == 0:
            log(f"  … {i}/{len(filings)}  (written {c['written']}, skipped {c['skipped']})")
    return c


def main() -> int:
    limit = int(_arg("--limit", "0") or 0)
    since = date.fromisoformat(_arg("--since", "2000-01-01"))
    pause = float(_arg("--pause", "0.3"))

    src = NSEFilingsSource(http=make_nse_getter())
    store = FundamentalsStore(STORE_ROOT)
    print(f"Harvesting NSE results filings since {since}"
          + (f" (limit {limit})" if limit else "") + " ...")
    c = run_harvest(src, store, since, limit=limit, pause=pause)
    print(f"\nDone. written {c['written']}, already-had {c['skipped']}, no-EPS "
          f"{c['no_eps']}, ambiguous {c['ambiguous']}, errors {c['errors']}.")
    print(f"Store now holds {len(store.symbols())} symbol(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
