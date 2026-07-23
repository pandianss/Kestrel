"""Daily reference-data snapshot job (G-43, D-15). Run once per trading day,
after the instruments master regenerates (~08:30 IST, doc 02 §4).

Idempotent: re-running on the same day with the same data is a no-op; a
*different* dataset for a date that already exists raises rather than
overwriting. Every day skipped is research data permanently lost.

    python scripts/snapshot_reference.py

Uses the dev StaticListSource until Kite auth is wired (doc 10 §2); swap in
KiteInstrumentsSource there with an authenticated client.
"""
from __future__ import annotations

import sys
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kestrel.data.reference import ReferenceSource, StaticListSource
from kestrel.data.snapshot import SnapshotConflictError, SnapshotStore

# Dev universe stand-in until Kite instruments are available.
DEV_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "ITC",
    "LT", "AXISBANK", "BHARTIARTL",
]

STORE_ROOT = "data/snapshots"


def snapshot_today(store: SnapshotStore, source: ReferenceSource, today: date) -> None:
    content = source.fetch()
    try:
        m = store.write(
            source.dataset, today, content, source=source.source_id, ext=source.ext
        )
        print(f"  snapshot {source.dataset} {today}: {m.size_bytes} bytes, "
              f"sha {m.sha256[:12]}  ({source.source_id})")
    except SnapshotConflictError as e:
        print(f"  CONFLICT (not overwritten): {e}")
        raise


def main() -> None:
    # today() is unavailable in some sandboxes; the job is called with an
    # explicit date in tests. For the CLI, derive it from the OS.
    import datetime as _dt

    today = _dt.date.today()
    store = SnapshotStore(STORE_ROOT)
    source = StaticListSource(DEV_SYMBOLS)
    print(f"Daily reference snapshot — {today}  (source: {source.source_id})")
    snapshot_today(store, source, today)
    dates = store.list_dates(source.dataset)
    print(f"  archive now holds {len(dates)} dated snapshot(s): "
          f"{dates[0]} .. {dates[-1]}")


if __name__ == "__main__":
    main()
