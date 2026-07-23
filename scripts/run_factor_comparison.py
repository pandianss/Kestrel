"""Compare the documented factors head to head — momentum vs low-volatility —
on the same universe, against the same honest controls.

The point is not the absolute CAGR (still survivorship-inflated on the Yahoo
static list; read the controls, per G-43). The point is the *comparison*:

  * Do the two factors actually behave differently, or are they the same bet?
    The correlation of their net-return streams answers that.
  * Which, if either, beats simply holding the survivors (information ratio)?

This is the harness the real verdict will run through once a point-in-time
universe (via the snapshotter) replaces the survivor list. See doc 11, G-01.

    python scripts/run_factor_comparison.py
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from kestrel.backtest.engine import run_backtest
from kestrel.backtest.metrics import information_ratio, perf_stats
from kestrel.data.universe import StaticUniverse
from kestrel.data.yahoo import load_monthly
from kestrel.strategies import low_volatility as lv
from kestrel.strategies import momentum as mom

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
    universe = StaticUniverse(list(stocks.columns))

    mcfg = mom.MomentumConfig(lookback_months=12, skip_months=1, n_hold=10)
    lcfg = lv.LowVolConfig(lookback_months=12, min_months=6, n_hold=10)

    mom_res = run_backtest(
        stocks, mom.momentum_scores(stocks, mcfg), universe,
        lambda row, tr: mom.target_holdings(row, tr, mcfg),
    )
    lv_res = run_backtest(
        stocks, lv.lowvol_scores(stocks, lcfg), universe,
        lambda row, tr: lv.target_holdings(row, tr, lcfg),
    )

    start = max(mom_res.net.first_valid_index(), lv_res.net.first_valid_index())
    ew_hold = ret.mean(axis=1).loc[start:]
    nifty_ret = nifty.pct_change().loc[start:] if nifty is not None else None

    print(f"\nMomentum vs Low-volatility — monthly rebalance, top-10, same universe")
    print(f"Sample: {start.date()} -> {mom_res.monthly.index.max().date()}")
    if mom_res.survivorship_biased:
        print("\n  ⚠️  SURVIVORSHIP-BIASED UNIVERSE (Yahoo static list).")
        print("      Absolute returns are NOT trustworthy — read the controls. (G-43)\n")

    def show(label: str, series: pd.Series) -> None:
        s = perf_stats(series.loc[start:])
        print(f"  {label:<42} {s}" if s else f"  {label:<42} (too short)")

    show("Momentum (NET)", mom_res.net)
    show("Low-volatility (NET)", lv_res.net)
    show("Equal-weight hold survivors  [control]", ew_hold)
    if nifty_ret is not None:
        show("NIFTY buy & hold  [honest market]", nifty_ret)

    # Are they actually different bets?
    joined = pd.concat(
        [mom_res.net.loc[start:], lv_res.net.loc[start:]], axis=1, keys=["mom", "lv"]
    ).dropna()
    corr = joined["mom"].corr(joined["lv"]) if len(joined) > 2 else float("nan")

    m_ann, m_ir = information_ratio(mom_res.net.loc[start:], ew_hold)
    l_ann, l_ir = information_ratio(lv_res.net.loc[start:], ew_hold)

    print(f"\n  Cross-factor correlation (net monthly): {corr:+.2f}")
    print(f"    (near +1 => same bet; lower => genuinely different exposures)")
    print(f"\n  Edge over holding the same survivors [the control that matters]:")
    print(f"    momentum : active {m_ann:+.1%}/yr,  IR {m_ir:+.2f}")
    print(f"    low-vol  : active {l_ann:+.1%}/yr,  IR {l_ir:+.2f}")
    print(f"    (IR near zero on this survivor pool means the factor timing adds")
    print(f"     little; the real test needs a point-in-time universe — G-43.)\n")


if __name__ == "__main__":
    main()
