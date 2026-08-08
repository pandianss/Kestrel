"""Backtest the four-pillar potential ranking — the honest test of the signal.

Monthly rebalance: each month-end, rank the universe by the SAME potential score
the dashboard shows, but computed point-in-time (only fundamentals public by that
date), hold the top N equal-weight, and realise next month's price return net of
real Zerodha costs + slippage. Compares the strategy to an equal-weight book of
the whole universe (does the ranking beat "own everything"?).

Uses the existing engine (kestrel/backtest/engine.py), which already enforces
point-in-time membership, no look-ahead, cost-on-turnover, and survivorship
accounting (G-48).

Caveats surfaced honestly:
  * Universe = names with BOTH price and fundamentals TODAY  to  survivorship-biased
    (delisted names absent); the engine flags this and it is printed.
  * Prices are Kite daily close; corporate-action adjustment is Kite's (G-08).
  * Promoter pillar is held neutral here (PIT promoter history not wired in).

    python scripts/backtest_ranking.py                 # top 20, full history
    python scripts/backtest_ranking.py --n 15 --start 2018-01-01
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kestrel.analysis.baskets import compute_potential_score
from kestrel.analysis.fundamentals_trend import analyse
from kestrel.backtest.engine import run_backtest
from kestrel.backtest.metrics import information_ratio, perf_stats
from kestrel.data.fundamentals_store import FundamentalsStore
from kestrel.data.universe import StaticUniverse

KD = Path("data/cache/kite")


def _arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def load_monthly_prices(symbols: list[str]) -> pd.DataFrame:
    cols = {}
    for s in symbols:
        f = KD / f"{s}_day.pkl"
        if not f.exists():
            continue
        df = pickle.loads(f.read_bytes())
        if isinstance(df, pd.DataFrame) and "close" in df.columns and len(df):
            cols[s] = df["close"]
    px = pd.DataFrame(cols).sort_index()
    return px.resample("ME").last()   # month-end close panel


def build_pit_scores(symbols: list[str], index: pd.DatetimeIndex,
                     store: FundamentalsStore, prices: pd.DataFrame | None = None,
                     valuation: bool = False) -> pd.DataFrame:
    """Potential score per (month-end, symbol), point-in-time (asof the date).
    With `valuation`, adds the 5th pillar using PIT P/E and P/B from the month-end
    price and the as-of EPS(TTM) / book value per share."""
    data = {}
    for s in symbols:
        recs = store.records(s)
        col = []
        for dt in index:
            t = analyse(s, recs, asof=dt.date())
            pe = pb = None
            if valuation and prices is not None:
                px = prices.at[dt, s] if s in prices.columns else None
                if px is not None and px == px:            # not NaN
                    if t.latest_eps and t.latest_eps > 0:
                        pe = px / t.latest_eps
                    if t.latest_book_value_per_share and t.latest_book_value_per_share > 0:
                        pb = px / t.latest_book_value_per_share
            col.append(compute_potential_score(t, pe=pe, pb=pb))
        data[s] = col
    return pd.DataFrame(data, index=index)


def top_n(n: int):
    def choose(scores_row: pd.Series, tradeable: list[str]) -> set:
        avail = scores_row.reindex(tradeable).dropna()
        return set(avail.sort_values(ascending=False).head(n).index)
    return choose


def top_n_quarterly(n: int):
    """Rebalance only at quarter-end months (Mar/Jun/Sep/Dec); hold in between.
    Fundamentals update quarterly, so monthly churn just pays cost for no new
    information. Holds the prior book, dropping only names no longer tradeable."""
    held: set = set()

    def choose(scores_row: pd.Series, tradeable: list[str]) -> set:
        nonlocal held
        dt = scores_row.name
        if (dt is not None and dt.month in (3, 6, 9, 12)) or not held:
            avail = scores_row.reindex(tradeable).dropna()
            held = set(avail.sort_values(ascending=False).head(n).index)
        else:
            held = {s for s in held if s in tradeable}
        return set(held)
    return choose


def _liquid_universe() -> set[str]:
    """NIFTY 500 symbols — a liquid, tradable gate. NOTE: this is a TODAY snapshot,
    so it swaps penny-stock/artifact noise for some look-ahead in membership; a
    proper PIT index history would be better, but this makes the benchmark sane."""
    p = Path("data/snapshots/constituents_nifty500/2026-07-25/data.csv")
    lines = p.read_text(encoding="utf-8").splitlines()
    idx = lines[0].split(",").index("Symbol")
    return {ln.split(",")[idx].strip() for ln in lines[1:] if ln.strip()}


def main() -> int:
    n = int(_arg("--n", "20") or 20)
    start = _arg("--start")
    liquid = "--liquid" in sys.argv
    store = FundamentalsStore("data/fundamentals")
    price_syms = {p.stem[:-4] for p in KD.glob("*_day.pkl")}
    syms = sorted(set(store.symbols()) & price_syms)
    if liquid:
        syms = sorted(set(syms) & _liquid_universe())
        print(f"[liquidity gate: NIFTY 500 -> {len(syms)} names]")
    print(f"Universe: {len(syms)} names with both price and fundamentals. "
          f"Loading prices...")
    prices = load_monthly_prices(syms)
    syms = [s for s in syms if s in prices.columns]
    prices = prices[syms]
    if start:
        prices = prices.loc[start:]
    valuation = "--valuation" in sys.argv
    quarterly = "--quarterly" in sys.argv
    cfg = (f"{'5-pillar (+valuation)' if valuation else '4-pillar'}, "
           f"{'quarterly' if quarterly else 'monthly'} rebalance")
    print(f"Building point-in-time scores [{cfg}]: {len(syms)} names x "
          f"{len(prices.index)} month-ends (this is the slow part)...")
    scores = build_pit_scores(syms, prices.index, store, prices=prices, valuation=valuation)

    holdings_fn = top_n_quarterly(n) if quarterly else top_n(n)
    res = run_backtest(prices, scores, StaticUniverse(syms), holdings_fn, capital=1_000_000.0)
    net = res.net.dropna()
    gross = res.gross.dropna()
    bench = prices.pct_change().mean(axis=1).reindex(net.index)   # equal-weight universe

    def cum(r):
        return float((1 + r).prod() - 1)

    print("\n" + "=" * 66)
    print(f"  RANKING BACKTEST — top {n}, net of costs")
    print(f"  config: {cfg}")
    print("=" * 66)
    print(f"  window: {net.index[0].date()}  to  {net.index[-1].date()}  "
          f"({len(net)} months)")
    print(f"  survivorship-biased universe: {res.survivorship_biased}  "
          f"(delisted names absent — results flatter than reality)")
    print(f"  smallest tradeable cross-section: {res.min_cross_section}   "
          f"missing marks: {res.missing_marks}")
    print("-" * 66)
    ps_net, ps_bench = perf_stats(net), perf_stats(bench)
    print(f"  {'':16}{'STRATEGY (net)':>18}{'BENCHMARK (EW)':>18}")
    print(f"  {'total return':16}{cum(net):>17.1%}{cum(bench):>18.1%}")
    if ps_net and ps_bench:
        print(f"  {'CAGR':16}{ps_net.cagr:>17.1%}{ps_bench.cagr:>18.1%}")
        print(f"  {'volatility':16}{ps_net.vol_annual:>17.1%}{ps_bench.vol_annual:>18.1%}")
        print(f"  {'Sharpe':16}{ps_net.sharpe:>17.2f}{ps_bench.sharpe:>18.2f}")
        print(f"  {'max drawdown':16}{ps_net.max_drawdown:>17.1%}{ps_bench.max_drawdown:>18.1%}")
        print(f"  {'t-stat (vs 0)':16}{ps_net.t_stat:>17.2f}{ps_bench.t_stat:>18.2f}")
    print(f"  {'avg turnover/mo':16}{res.monthly['turnover'].mean():>17.1%}")
    print("-" * 66)
    # The honest control under survivorship bias: does the ranking beat the SAME
    # pool, equal-weighted? Active return + information ratio measure exactly that.
    active, ir = information_ratio(net, bench)
    print(f"  active return (strategy - benchmark): {active:+.1%}/yr   info ratio: {ir:.2f}")
    print("=" * 66)
    print("  NOTE: survivorship bias + Kite corporate-action adjustment (G-08) +")
    print("  neutral promoter pillar. Directional evidence, not a P&L promise.")
    print("  The active return / IR vs the same pool is the number that survives")
    print("  the survivorship caveat — read that, not the headline CAGR.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
