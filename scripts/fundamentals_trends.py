"""Compare companies' fundamentals over time — who is improving, who declining.

Reads the accumulated fundamentals store and ranks companies by their EPS trend
(least-squares slope over the stored quarters), showing YoY and QoQ growth.

    python scripts/fundamentals_trends.py            # all companies in the store
    python scripts/fundamentals_trends.py RELIANCE INFY TCS

Backfill history first with scripts/backfill_fundamentals.py — trend needs
several quarters per company.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kestrel.analysis.fundamentals_trend import compare
from kestrel.data.fundamentals_store import FundamentalsStore

STORE_ROOT = "data/fundamentals"


def _pct(x: float | None) -> str:
    return "  —  " if x is None else f"{x:+6.0%}"


def main() -> int:
    syms = [a for a in sys.argv[1:] if not a.startswith("--")] or None
    store = FundamentalsStore(STORE_ROOT)
    trends = compare(store, syms)
    measurable = [t for t in trends if t.direction != "insufficient"]

    print(f"\nFundamental trend — {len(measurable)} company(ies) with ≥2 quarters "
          f"({len(trends) - len(measurable)} need more history)\n")
    if not measurable:
        print("  Not enough history yet. Backfill with scripts/backfill_fundamentals.py.")
        return 0

    hdr = f"  {'symbol':<12} {'dir':<10} {'qtrs':>4} {'latest EPS':>10} {'QoQ':>7} {'YoY':>7}  {'slope/qtr':>9}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    arrow = {"improving": "▲ up", "declining": "▼ down", "flat": "► flat"}
    for t in measurable:
        print(f"  {t.symbol:<12} {arrow.get(t.direction, t.direction):<10} {t.n:>4} "
              f"{(t.latest_eps or 0):>10.2f} {_pct(t.qoq_growth):>7} {_pct(t.yoy_growth):>7}  "
              f"{(t.slope or 0):>+9.3f}")

    up = [t.symbol for t in measurable if t.direction == "improving"]
    dn = [t.symbol for t in measurable if t.direction == "declining"]
    print(f"\n  Improving: {', '.join(up) or '—'}")
    print(f"  Declining: {', '.join(dn) or '—'}")
    print("\n  EPS is current-quarter, consolidated where available. Trend is the "
          "least-squares slope over the stored quarters.")
    print("  ⚠️  Per-share EPS is NOT bonus/split-adjusted (G-49): a bonus/split "
          "distorts QoQ/YoY across its boundary — read the multi-quarter slope, "
          "not a single QoQ. A PAT-based (share-count-invariant) trend is the "
          "robust fix; see docs/11 G-49.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
