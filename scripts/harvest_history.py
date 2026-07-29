"""Batch historical daily price data harvester for NSE equity instruments.

Fetches real daily OHLCV candles from the Kite Connect API for equity instruments
found in the latest instruments snapshot. Rate-limited and **resumable**:
skips symbols whose cached data is already up-to-date.

Usage:
    python scripts/harvest_history.py                        # All NSE EQ instruments from 2015
    python scripts/harvest_history.py --limit 10             # Test batch of 10
    python scripts/harvest_history.py --symbols INFY,TCS,RELIANCE
    python scripts/harvest_history.py --since 2020-01-01
"""
from __future__ import annotations

import csv
import io
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kestrel.data.kite_history import InstrumentResolver, KiteHistory
from kestrel.data.snapshot import SnapshotStore
from kestrel.kite.tokenstore import FileTokenStore

TOKEN_PATH = "data/secrets/kite_token.json"
SNAPSHOT_ROOT = "data/snapshots"
CACHE_DIR = Path("data/cache/kite")


def _arg(flag: str, default: str | None = None) -> str | None:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def nse_equity_row(r: dict) -> bool:
    return (r.get("exchange") == "NSE" and
            r.get("segment") == "NSE" and
            r.get("instrument_type") == "EQ")


def _is_up_to_date(last_cached_date: date, to_date: date) -> bool:
    if last_cached_date >= to_date:
        return True
    days_diff = (to_date - last_cached_date).days
    # If last cached candle was Friday (weekday 4) and today is weekend/Mon before open (<= 3 days later):
    if days_diff <= 3 and last_cached_date.weekday() == 4:
        return True
    return False


def run_harvest_history(
    symbols: list[str],
    from_date: date,
    to_date: date,
    hist: KiteHistory,
    resolver: InstrumentResolver,
    *,
    pause: float = 0.35,
    limit: int = 0,
    log=print,
) -> dict:
    import pandas as pd
    from datetime import timedelta

    if limit > 0:
        symbols = symbols[:limit]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    c = dict(fetched=0, updated=0, skipped=0, empty=0, errors=0, total_bars=0)

    log(f"Starting history harvest for {len(symbols)} symbol(s) ({from_date} → {to_date}) ...")

    def _progress(i):
        if i % 10 == 0 or i == len(symbols):
            log(f"  … {i}/{len(symbols)} (new {c['fetched']}, updated {c['updated']}, "
                f"skipped {c['skipped']}, +{c['total_bars']:,} bars)")

    for i, sym in enumerate(symbols, 1):
        out_file = CACHE_DIR / f"{sym}_day.pkl"
        df_existing, fetch_from = None, from_date

        # Already cached? Fetch only the MISSING TAIL, never re-download history.
        if out_file.exists():
            try:
                df_existing = pd.read_pickle(out_file)
            except Exception:
                df_existing = None
            if df_existing is not None and not df_existing.empty:
                last = df_existing.index[-1].date()
                if _is_up_to_date(last, to_date):
                    c["skipped"] += 1
                    _progress(i)
                    continue
                fetch_from = last + timedelta(days=1)   # incremental: just the new bars

        try:
            token = resolver.token(sym)
        except KeyError:
            c["errors"] += 1
            continue

        try:
            df_new = hist.fetch_candles(token, fetch_from, to_date)
        except Exception as e:
            c["errors"] += 1
            log(f"  [ERROR] {sym} (token {token}): {e}")
            time.sleep(pause)
            _progress(i)
            continue

        if df_new.empty:
            c["skipped" if df_existing is not None else "empty"] += 1
        elif df_existing is not None and not df_existing.empty:
            df = pd.concat([df_existing, df_new])
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df.to_pickle(out_file)
            c["updated"] += 1
            c["total_bars"] += len(df_new)
        else:
            df_new.to_pickle(out_file)
            c["fetched"] += 1
            c["total_bars"] += len(df_new)

        time.sleep(pause)
        _progress(i)

    return c


def main() -> int:
    now = datetime.now(timezone.utc)
    to_date = now.date()

    since_str = _arg("--since", "2015-01-01")
    from_date = date.fromisoformat(since_str) if since_str else date(2015, 1, 1)
    limit = int(_arg("--limit", "0") or 0)
    pause = float(_arg("--pause", "0.35") or "0.35")
    symbols_arg = _arg("--symbols")

    # 1. Load active session token
    store = FileTokenStore(TOKEN_PATH)
    if store.load_valid(now) is None:
        print("No valid Kite token — run login_starter.ps1 or scripts/kite_login.py first.")
        return 3

    # 2. Resolve instruments snapshot
    snap_store = SnapshotStore(SNAPSHOT_ROOT)
    snap_dates = snap_store.list_dates("instruments")
    if not snap_dates:
        print("No instruments snapshot found in data/snapshots/. Run snapshot_reference.py first.")
        return 1

    latest_date = snap_dates[-1]
    resolver = InstrumentResolver.from_snapshot_store(snap_store, to_date)

    # 3. Determine symbol list
    if symbols_arg:
        target_symbols = [s.strip().upper() for s in symbols_arg.split(",") if s.strip()]
    else:
        # Load all NSE EQ instruments from latest snapshot
        raw_csv = snap_store.read("instruments", latest_date)
        rows = list(csv.DictReader(io.StringIO(raw_csv.decode("utf-8"))))
        target_symbols = sorted(r["tradingsymbol"] for r in rows if nse_equity_row(r))

    hist = KiteHistory.from_token_store(store, now=now)
    c = run_harvest_history(target_symbols, from_date, to_date, hist, resolver, pause=pause, limit=limit)

    print(f"\nHarvest Complete.")
    print(f"  New (full history): {c['fetched']} symbols")
    print(f"  Updated (incremental tail only): {c['updated']} symbols")
    print(f"  Skipped (already up to date): {c['skipped']}")
    print(f"  +{c['total_bars']:,} new bars.  Empty {c['empty']}, errors {c['errors']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
