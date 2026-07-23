"""Reproduce the 2026-07-23 momentum finding — and its honest caveat.

Runs cross-sectional momentum on a static (survivorship-biased) NSE large-cap
universe from Yahoo, against two controls:

  * equal-weight buy-and-hold of the SAME survivors — strips most of the
    survivorship bias, so momentum's edge over *this* is the real signal;
  * NIFTY buy-and-hold — the honest market return.

The headline momentum CAGR looks spectacular and is mostly bias. The long-short
spread and the information ratio vs the survivor control are what tell the
truth. See doc 11, G-01/G-43.

    python scripts/run_momentum.py
"""
from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console is cp1252 by default

import pandas as pd

from kestrel.backtest.engine import run_backtest
from kestrel.backtest.metrics import information_ratio, perf_stats
from kestrel.data.universe import StaticUniverse
from kestrel.data.yahoo import load_monthly
from kestrel.strategies.momentum import (
    MomentumConfig,
    momentum_scores,
    target_holdings,
)

# NSE large caps (as of 2026 — hence survivorship-biased; that is the point).
UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC",
    "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", "ASIANPAINT", "MARUTI",
    "SUNPHARMA", "TITAN", "BAJFINANCE", "NESTLEIND", "WIPRO", "ULTRACEMCO",
    "ONGC", "NTPC", "POWERGRID", "M&M", "TATASTEEL", "JSWSTEEL", "HCLTECH",
    "TECHM", "BAJAJFINSV", "ADANIPORTS", "COALINDIA", "GRASIM", "HINDALCO",
    "DRREDDY", "CIPLA", "EICHERMOT", "BRITANNIA", "HEROMOTOCO", "DIVISLAB",
    "BPCL", "SHREECEM", "INDUSINDBK", "UPL", "GAIL", "DABUR", "PIDILITIND",
    "GODREJCP", "AMBUJACEM",
]


def main() -> None:
    px = load_monthly(UNIVERSE + ["^NSEI"])
    nifty = px["^NSEI"].dropna() if "^NSEI" in px else None
    stocks = px.drop(columns=[c for c in ["^NSEI"] if c in px])
    ret = stocks.pct_change()

    cfg = MomentumConfig(lookback_months=12, skip_months=1, n_hold=10)
    scores = momentum_scores(stocks, cfg)
    universe = StaticUniverse(list(stocks.columns))

    def holdings_fn(scores_row: pd.Series, tradeable: list[str]) -> set:
        return target_holdings(scores_row, tradeable, cfg)

    res = run_backtest(stocks, scores, universe, holdings_fn)

    start = res.net.first_valid_index()
    ew_hold = ret.mean(axis=1).loc[start:]                # control 1
    nifty_ret = nifty.pct_change().loc[start:] if nifty is not None else None

    print(f"\nMomentum {cfg.lookback_months}-{cfg.skip_months}, top-{cfg.n_hold}, "
          f"monthly rebalance")
    print(f"Sample: {start.date()} -> {res.monthly.index.max().date()}   "
          f"avg turnover {res.monthly['turnover'].loc[start:].mean():.0%}/mo")
    if res.survivorship_biased:
        print("\n  ⚠️  SURVIVORSHIP-BIASED UNIVERSE (Yahoo static list).")
        print("      Absolute returns are NOT trustworthy. Read the controls,")
        print("      not the headline CAGR. (doc 11, G-43)\n")

    def show(label: str, series: pd.Series) -> None:
        s = perf_stats(series.loc[start:])
        print(f"  {label:<40} {s}" if s else f"  {label:<40} (too short)")

    show("Momentum (GROSS)", res.gross)
    show("Momentum (NET of costs)", res.net)
    show("Equal-weight hold survivors  [control]", ew_hold)
    if nifty_ret is not None:
        show("NIFTY buy & hold  [honest market]", nifty_ret)

    ann, ir = information_ratio(res.net.loc[start:], ew_hold)
    print(f"\n  The control that matters — momentum NET vs holding the same survivors:")
    print(f"    active return {ann:+.1%}/yr,  information ratio {ir:.2f}")
    print(f"    (IR near zero => momentum TIMING adds ~nothing on this pool;")
    print(f"     the fat CAGR is the survivors, not the factor.)\n")


if __name__ == "__main__":
    main()
