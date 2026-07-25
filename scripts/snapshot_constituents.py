"""Daily index-constituents snapshot (G-43) — the clean stock universe.

Snapshots NSE's published index membership immutably (D-15), so point-in-time
stock membership accumulates going forward. Add it to the morning routine
alongside the instruments snapshot.

    python scripts/snapshot_constituents.py            # nifty500 (default)
    python scripts/snapshot_constituents.py nifty50

Needs no Kite token — NSE index CSVs are public. Idempotent per day.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kestrel.data.constituents import NSEConstituentsSource, parse_symbols
from kestrel.data.snapshot import SnapshotConflictError, SnapshotStore
from kestrel.kite.auth import IST

STORE_ROOT = "data/snapshots"


def main() -> int:
    index = sys.argv[1] if len(sys.argv) > 1 else "nifty500"
    today = datetime.now(timezone.utc).astimezone(IST).date()
    store = SnapshotStore(STORE_ROOT)
    src = NSEConstituentsSource(index)

    print(f"Index constituents snapshot — {index} — {today}")
    try:
        content = src.fetch()
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ fetch failed: {e}")
        return 1

    n = len(parse_symbols(content))
    try:
        m = store.write(src.dataset, today, content, source=src.source_id, ext="csv")
        print(f"  {n} stocks, {m.size_bytes} bytes, sha {m.sha256[:12]}  ({src.source_id})")
    except SnapshotConflictError as e:
        print(f"  CONFLICT (not overwritten): {e}")
        return 2
    dates = store.list_dates(src.dataset)
    print(f"  archive now holds {len(dates)} dated snapshot(s): {dates[0]} .. {dates[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
