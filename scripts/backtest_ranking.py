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


def _industry_map() -> dict[str, str]:
    """Symbol -> industry, from the NIFTY 500 constituents snapshot (has an
    Industry column for every liquid name)."""
    p = Path("data/snapshots/constituents_nifty500/2026-07-25/data.csv")
    lines = p.read_text(encoding="utf-8").splitlines()
    hdr = lines[0].split(",")
    si, ii = hdr.index("Symbol"), hdr.index("Industry")
    out = {}
    for ln in lines[1:]:
        parts = ln.split(",")
        if len(parts) > max(si, ii):
            out[parts[si].strip()] = parts[ii].strip()
    return out


def _sector_relative_valuation(ey: pd.DataFrame, by: pd.DataFrame,
                               industry: dict[str, str]) -> pd.DataFrame:
    """Per date, rank each name's cheapness WITHIN its industry (percentile of
    earnings-yield and book-yield among sector peers that date; higher = cheaper).
    Returns a [date x symbol] valuation score in 0..1 (NaN where no peers/data)."""
    ind = pd.Series({s: industry.get(s, "?") for s in ey.columns})
    out = pd.DataFrame(index=ey.index, columns=ey.columns, dtype=float)
    for dt in ey.index:
        df = pd.DataFrame({"ey": ey.loc[dt], "by": by.loc[dt], "ind": ind})
        eyr = df.groupby("ind")["ey"].rank(pct=True)
        byr = df.groupby("ind")["by"].rank(pct=True)
        out.loc[dt] = pd.concat([eyr, byr], axis=1).mean(axis=1)
    return out


def build_pit_scores(symbols: list[str], index: pd.DatetimeIndex,
                     store: FundamentalsStore, prices: pd.DataFrame | None = None,
                     valuation: bool = False, sector_val: bool = False,
                     industry: dict[str, str] | None = None) -> pd.DataFrame:
    """Potential score per (month-end, symbol), point-in-time (asof the date).
    valuation → 5th pillar from absolute P/E,P/B. sector_val → the valuation
    pillar is instead a within-industry cheapness rank (needs `industry`)."""
    # Pass 1: cache the as-of Trend and the two yields per (symbol, date).
    trends: dict[str, list] = {}
    ey_cols: dict[str, list] = {}
    by_cols: dict[str, list] = {}
    for s in symbols:
        recs = store.records(s)
        tl, eyl, byl = [], [], []
        for dt in index:
            t = analyse(s, recs, asof=dt.date())
            tl.append(t)
            px = prices.at[dt, s] if (prices is not None and s in prices.columns) else None
            ok = px is not None and px == px and px > 0
            eyl.append((t.latest_eps / px) if (ok and t.latest_eps is not None) else float("nan"))
            byl.append((t.latest_book_value_per_share / px)
                       if (ok and t.latest_book_value_per_share and t.latest_book_value_per_share > 0)
                       else float("nan"))
        trends[s], ey_cols[s], by_cols[s] = tl, eyl, byl

    valdf = None
    if sector_val and industry is not None:
        ey = pd.DataFrame(ey_cols, index=index)
        by = pd.DataFrame(by_cols, index=index)
        valdf = _sector_relative_valuation(ey, by, industry)

    # Pass 2: combine.
    data = {}
    for s in symbols:
        col = []
        for i, dt in enumerate(index):
            t = trends[s][i]
            if valdf is not None:
                vs = valdf.at[dt, s]
                col.append(compute_potential_score(t, valuation_score=(vs if vs == vs else None)))
            elif valuation:
                ey_v, by_v = ey_cols[s][i], by_cols[s][i]
                pe = (1.0 / ey_v) if ey_v == ey_v and ey_v > 0 else None
                pb = (1.0 / by_v) if by_v == by_v and by_v > 0 else None
                col.append(compute_potential_score(t, pe=pe, pb=pb))
            else:
                col.append(compute_potential_score(t))
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
    import json
    from datetime import date as _date

    from kestrel.data.universe import PointInTimeUniverse
    n = int(_arg("--n", "20") or 20)
    start = _arg("--start")
    liquid = "--liquid" in sys.argv
    pit = "--pit-universe" in sys.argv
    store = FundamentalsStore("data/fundamentals")
    price_syms = {p.stem[:-4] for p in KD.glob("*_day.pkl")}
    syms = sorted(set(store.symbols()) & price_syms)

    universe = None
    residual_note = ""
    if pit:
        raw = json.loads(Path("data/snapshots/nifty500_membership.json").read_text(encoding="utf-8"))
        membership = {_date.fromisoformat(k): v for k, v in raw.items()}
        ever = {s for v in membership.values() for s in v}
        syms = sorted(ever & price_syms & set(store.symbols()))
        no_price = sorted(ever - price_syms)   # ex-members we can't price (delisted/unavailable)
        universe = PointInTimeUniverse(membership)
        residual_note = (f"  PIT membership: {len(membership)} dated snapshots "
                         f"({min(membership)}..{max(membership)}), {len(ever)} ever-members.\n"
                         f"  RESIDUAL survivorship: {len(no_price)} ever-members have no price "
                         f"(delisted/unavailable) — silently excluded. Membership look-ahead FIXED;\n"
                         f"  delisted-price survivorship NOT (Kite only serves live instruments, G-43).")
        print(f"[PIT universe: {len(syms)} names with price+fundamentals from "
              f"{len(ever)} ever-members]")
    elif liquid:
        syms = sorted(set(syms) & _liquid_universe())
        print(f"[liquidity gate: NIFTY 500 (today) -> {len(syms)} names]")
    print(f"Universe: {len(syms)} names with both price and fundamentals. "
          f"Loading prices...")
    prices = load_monthly_prices(syms)
    syms = [s for s in syms if s in prices.columns]
    prices = prices[syms]
    if start:
        prices = prices.loc[start:]
    sector_val = "--sector-val" in sys.argv
    valuation = "--valuation" in sys.argv or sector_val
    quarterly = "--quarterly" in sys.argv
    val_label = ("+sector-relative valuation" if sector_val
                 else "+absolute valuation" if valuation else "no valuation")
    cfg = (f"{'5-pillar' if valuation else '4-pillar'} ({val_label}), "
           f"{'quarterly' if quarterly else 'monthly'} rebalance")
    industry = _industry_map() if sector_val else None
    print(f"Building point-in-time scores [{cfg}]: {len(syms)} names x "
          f"{len(prices.index)} month-ends (this is the slow part)...")
    scores = build_pit_scores(syms, prices.index, store, prices=prices,
                              valuation=valuation, sector_val=sector_val, industry=industry)

    base_fn = top_n_quarterly(n) if quarterly else top_n(n)
    holdings_log: dict[str, list[str]] = {}

    def holdings_fn(scores_row, tradeable):
        picks = base_fn(scores_row, tradeable)
        dt = getattr(scores_row, "name", None)
        if dt is not None:
            holdings_log[dt.strftime("%Y-%m")] = sorted(picks)
        return picks

    if universe is None:
        universe = StaticUniverse(syms)
    res = run_backtest(prices, scores, universe, holdings_fn, capital=1_000_000.0)
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
    if residual_note:
        print(residual_note)
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

    if "--save" in sys.argv and ps_net and ps_bench:
        from datetime import datetime
        eq_s = (1 + net).cumprod()
        eq_b = (1 + bench.fillna(0)).cumprod().reindex(eq_s.index)
        out = {
            "generated": datetime.now().isoformat(timespec="seconds"),
            "config": cfg + (", PIT NIFTY 500" if pit else (", liquid" if liquid else "")),
            "window": f"{net.index[0].date()} to {net.index[-1].date()}",
            "months": len(net), "n": n,
            "dates": [d.strftime("%Y-%m") for d in eq_s.index],
            "strategy_equity": [round(float(x), 4) for x in eq_s],
            "benchmark_equity": [round(float(x), 4) for x in eq_b],
            "stats": {
                "strategy": {"cagr": ps_net.cagr, "sharpe": ps_net.sharpe,
                             "maxdd": ps_net.max_drawdown, "tstat": ps_net.t_stat,
                             "total": cum(net)},
                "benchmark": {"cagr": ps_bench.cagr, "sharpe": ps_bench.sharpe,
                              "maxdd": ps_bench.max_drawdown, "total": cum(bench)},
                "active": active, "ir": ir,
                "turnover": float(res.monthly["turnover"].mean()),
            },
            "survivorship_biased": bool(res.survivorship_biased),
            "caveat": ("Delisted-price survivorship remains (Kite serves only live "
                       "instruments); results modestly flattered."),
        }
        # Trade timeline: the change-points where the book actually turned over
        # (a name leaving the top-N IS the exit — the strategy exits by rotation).
        trades, prev = [], set()
        for m in sorted(holdings_log):
            cur = set(holdings_log[m])
            if cur != prev:
                trades.append({"date": m, "bought": sorted(cur - prev),
                               "sold": sorted(prev - cur), "n": len(cur)})
                prev = cur
        out["trades"] = trades
        out["current_holdings"] = sorted(prev)
        Path("data/backtest_results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("\n  saved -> data/backtest_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
