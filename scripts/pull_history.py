"""Pull real Kite daily history for one symbol and cache it.

Uses the token you minted (scripts/kite_login.py) and the instruments snapshot
you captured (scripts/snapshot_reference.py) — the symbol→token map comes from
the snapshot, the candles from Kite's historical API.

    python scripts/pull_history.py                 # RELIANCE, from 2015
    python scripts/pull_history.py INFY 2018-01-01

⚠️ Real prices, but read with the same caveats (kite_history.py):
  * survivorship — today's tokens only, so a universe is still survivor-biased;
  * dividends — Kite adjusts splits/bonuses only, so ex-div gaps are artefacts.
This is for calibration and real-price runs, not a clean factor verdict.
"""
from __future__ import annotations

import sys
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


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    frm = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2015, 1, 1)
    now = datetime.now(timezone.utc)
    to = now.date()

    store = FileTokenStore(TOKEN_PATH)
    if store.load_valid(now) is None:
        print("No valid Kite token — run scripts/kite_login.py first.")
        return 3

    resolver = InstrumentResolver.from_snapshot_store(SnapshotStore(SNAPSHOT_ROOT), to)
    try:
        token = resolver.token(symbol)
    except KeyError:
        print(f"{symbol} not found in the instruments snapshot (NSE EQ). "
              f"Check the symbol, or capture a fresh snapshot.")
        return 1

    hist = KiteHistory.from_token_store(store, now=now)
    print(f"Pulling {symbol} (token {token}) daily candles {frm} → {to} ...")
    df = hist.fetch_candles(token, frm, to)
    if df.empty:
        print("  no candles returned.")
        return 1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"{symbol}_day.pkl"
    df.to_pickle(out)
    print(f"  {len(df)} bars, {df.index[0].date()} → {df.index[-1].date()}")
    print(f"  last close ₹{df.iloc[-1]['close']:,.2f}   cached → {out}")
    print(f"\n  Real prices — mind the survivorship and dividend caveats above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
