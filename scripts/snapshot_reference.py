"""Daily reference-data snapshot job (G-43, D-15). Run once per trading day,
after the instruments master regenerates (~08:30 IST, doc 02 §4).

Idempotent: re-running on the same day with the same data is a no-op; a
*different* dataset for a date that already exists raises rather than
overwriting. Every day skipped is research data permanently lost.

    python scripts/snapshot_reference.py             # dev fallback allowed
    python scripts/snapshot_reference.py --require-live   # scheduled/prod mode

In `--require-live` mode (also `KESTREL_REQUIRE_LIVE=1`) the job refuses the dev
fallback: with no valid Kite token it exits non-zero *without writing anything*,
so a scheduler never poisons the real archive with dev data. That non-zero exit
is the signal to the operator that the morning token mint (scripts/kite_login.py)
has not happened yet.
"""
from __future__ import annotations

import os
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


class NoLiveTokenError(RuntimeError):
    """Raised in require-live mode when no valid token is available. A caller
    (scheduler) should treat this as 'the operator hasn't logged in yet', not
    as a code fault."""


def choose_source(now: datetime, *, require_live: bool) -> ReferenceSource:
    """Prefer the real Kite instruments dump when a valid token is stored.

    In require-live mode, no token is a hard error — never a silent dev
    fallback, because a scheduled run archiving dev data as a real trading-day
    snapshot would corrupt the point-in-time record the whole design depends on.
    """
    token = FileTokenStore(TOKEN_PATH).load_valid(now)
    if token is not None:
        print(f"  using live Kite instruments ({token.masked()})")
        return KiteInstrumentsSource(token.api_key, token.access_token)
    if require_live:
        raise NoLiveTokenError(
            "no valid Kite token and --require-live is set — refusing to archive "
            "DEV data as a real snapshot. Run scripts/kite_login.py to mint today's "
            "token, then re-run. (Nothing was written.)"
        )
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


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    require_live = "--require-live" in argv or os.environ.get("KESTREL_REQUIRE_LIVE") == "1"

    now = datetime.now(timezone.utc)
    today = now.astimezone(IST).date()   # trading day is an IST calendar day
    store = SnapshotStore(STORE_ROOT)
    print(f"Daily reference snapshot — {today}"
          f"{'  [require-live]' if require_live else ''}")
    try:
        source = choose_source(now, require_live=require_live)
    except NoLiveTokenError as e:
        print(f"  ✗ {e}")
        return 3   # distinct code: 'operator action needed', not a crash
    snapshot_today(store, source, today)
    dates = store.list_dates(source.dataset)
    print(f"  archive now holds {len(dates)} dated snapshot(s): "
          f"{dates[0]} .. {dates[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
