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
from datetime import date, datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kestrel.data.reference import (
    KiteInstrumentsSource,
    ReferenceSource,
    StaticListSource,
)
from kestrel.data.snapshot import SnapshotConflictError, SnapshotStore
from kestrel.kite.auth import IST
from kestrel.kite.tokenstore import FileTokenStore

# Dev universe stand-in used only when no Kite token is available.
DEV_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "ITC",
    "LT", "AXISBANK", "BHARTIARTL",
]

STORE_ROOT = "data/snapshots"
TOKEN_PATH = "data/secrets/kite_token.json"


def choose_source(now: datetime) -> ReferenceSource:
    """Prefer the real Kite instruments dump when a valid token is stored; fall
    back to the dev source so the pipeline still runs before auth is wired.
    Note the fallback loudly — a dev snapshot must never be mistaken for real
    reference data."""
    token = FileTokenStore(TOKEN_PATH).load_valid(now)
    if token is not None:
        print(f"  using live Kite instruments ({token.masked()})")
        return KiteInstrumentsSource(token.api_key, token.access_token)
    print("  ⚠️  no valid Kite token — falling back to DEV static list. "
          "Run scripts/kite_login.py to capture real reference data.")
    return StaticListSource(DEV_SYMBOLS)


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
    now = datetime.now(timezone.utc)
    today = now.astimezone(IST).date()   # trading day is an IST calendar day
    store = SnapshotStore(STORE_ROOT)
    print(f"Daily reference snapshot — {today}")
    source = choose_source(now)
    snapshot_today(store, source, today)
    dates = store.list_dates(source.dataset)
    print(f"  archive now holds {len(dates)} dated snapshot(s): "
          f"{dates[0]} .. {dates[-1]}")


if __name__ == "__main__":
    main()
