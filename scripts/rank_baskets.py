"""Rank all instruments from most potential to least, and group into factor baskets.

Evaluates all ingested companies in the point-in-time fundamentals store (data/fundamentals),
computes normalized potential scores, groups instruments into four factor baskets,
and saves the output to data/baskets_ranking.json.

Usage:
    python scripts/rank_baskets.py                        # Rank all instruments in store
    python scripts/rank_baskets.py --top 10               # Show top 10 per basket in CLI
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kestrel.analysis.baskets import rank_and_group_baskets
from kestrel.analysis.fundamentals_trend import compare
from kestrel.data.fundamentals_store import FundamentalsStore
from kestrel.data.relations_store import RelationsStore

STORE_ROOT = "data/fundamentals"
RELATIONS_ROOT = "data/relations"
OUTPUT_FILE = Path("data/baskets_ranking.json")


def _arg(flag: str, default: str | None = None) -> str | None:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def _latest_close(symbol: str) -> float | None:
    """Latest daily close from the Kite cache — the same price source the backtest
    used, so the displayed signal matches the tested one. Offline, no token."""
    import pickle
    f = Path("data/cache/kite") / f"{symbol}_day.pkl"
    if not f.exists():
        return None
    try:
        df = pickle.loads(f.read_bytes())
        c = df["close"].dropna()
        return float(c.iloc[-1]) if len(c) else None
    except Exception:  # noqa: BLE001
        return None


def _industry_map() -> dict[str, str]:
    p = Path("data/snapshots/constituents_nifty500/2026-07-25/data.csv")
    if not p.exists():
        return {}
    lines = p.read_text(encoding="utf-8").splitlines()
    hdr = lines[0].split(",")
    try:
        si, ii = hdr.index("Symbol"), hdr.index("Industry")
    except ValueError:
        return {}
    out = {}
    for ln in lines[1:]:
        parts = ln.split(",")
        if len(parts) > max(si, ii):
            out[parts[si].strip()] = parts[ii].strip()
    return out


def _valuation_scores(trends) -> dict[str, float]:
    """Within-industry cheapness score per symbol from current price + as-of
    EPS(TTM)/BVPS. Only names with price AND industry get a score."""
    from kestrel.analysis.baskets import sector_relative_valuation
    industry = _industry_map()
    yields: dict[str, tuple[float | None, float | None]] = {}
    for t in trends:
        if t.symbol not in industry:
            continue
        px = _latest_close(t.symbol)
        if not px or px <= 0:
            continue
        ey = (t.latest_eps / px) if t.latest_eps is not None else None
        bv = t.latest_book_value_per_share
        by = (bv / px) if (bv and bv > 0) else None
        if ey is not None or by is not None:
            yields[t.symbol] = (ey, by)
    return sector_relative_valuation(yields, industry)


def main() -> int:
    top_limit = int(_arg("--top", "10") or "10")
    store_dir = _arg("--store", STORE_ROOT) or STORE_ROOT
    rel_dir = _arg("--relations", RELATIONS_ROOT) or RELATIONS_ROOT

    store = FundamentalsStore(store_dir)
    rel_store = RelationsStore(rel_dir) if Path(rel_dir).exists() else None
    syms = store.symbols()

    if not syms:
        print(f"No symbols found in fundamentals store ({store_dir}). Run harvest_fundamentals.py first.")
        return 1

    print(f"Evaluating and ranking {len(syms)} symbol(s) from {store_dir} ...")

    # 1. Compute multi-quarter trends for all instruments
    trends = compare(store, syms)

    # 1b. Sector-relative valuation pillar (the backtested config): current price
    # + industry -> within-industry cheapness. Names without price/industry fall
    # back to the 4-pillar score.
    valuation_scores = _valuation_scores(trends)
    print(f"  valuation pillar active for {len(valuation_scores)} name(s) "
          f"(current price x industry)")

    # 2. Score & Group into baskets (5-pillar where valuation is available)
    baskets = rank_and_group_baskets(trends, rel_store, valuation_scores=valuation_scores)

    # 3. Serialise output JSON
    serialised_output: dict[str, list[dict]] = {}
    total_count = 0

    for b_name, items in baskets.items():
        total_count += len(items)
        serialised_output[b_name] = [item.to_dict() for item in items]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(serialised_output, indent=2), encoding="utf-8")
    print(f"Saved rankings to {OUTPUT_FILE.resolve()} ({total_count} total instruments ranked)\n")

    # 4. Print summary table to CLI
    for b_name, items in baskets.items():
        badge = items[0].basket_badge if items else ""
        print(f"============================================================")
        print(f"  {badge} {b_name} ({len(items)} instruments)")
        print(f"============================================================")
        if not items:
            print("  (no instruments in this basket)")
            continue

        print(f"  {'Symbol':<12} {'Potential':<12} {'EPS Slope':<12} {'ROE':<10} {'D/E':<10} {'Promoter %':<12}")
        print(f"  {'-'*12} {'-'*12} {'-'*12} {'-'*10} {'-'*10} {'-'*12}")
        for item in items[:top_limit]:
            d = item.to_dict()
            slope_str = f"{item.slope:+.2f}" if item.slope is not None else "—"
            print(f"  {item.symbol:<12} {d['potential_pct']:<12} {slope_str:<12} {d['roe_pct']:<10} {d['d2e_ratio']:<10} {d['promoter_pct']:<12}")
        if len(items) > top_limit:
            print(f"  … and {len(items) - top_limit} more\n")
        else:
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
