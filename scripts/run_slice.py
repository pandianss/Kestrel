"""The vertical slice (doc 09): one instrument, a deterministic entry rule, the
real fill simulator and Position Manager, no LLMs.

The purpose is NOT to show an edge — the entry rule here (a simple trend
filter) is a placeholder. The purpose is to exercise the two things document
review structurally cannot catch, and that only appear once you carry a real
position: the **deterministic exit path** (G-28) and **cash/margin accounting**
(G-29). Every rupee of cost is charged, every exit fires from code, and the
book can never spend money it does not have.

Sequencing is strict end-of-day, no look-ahead:
  * the entry signal is computed on day t's close and can only fill at t+1's open;
  * once open, the position's ExitPlan is evaluated against each day's bar,
    including its own entry day (a position can be stopped out the day it opens).

    python scripts/run_slice.py            # default: RELIANCE
    python scripts/run_slice.py INFY
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from kestrel.data.yahoo import load_daily_ohlc

_KITE_CACHE = Path("data/cache/kite")


def _load(symbol: str) -> tuple[pd.DataFrame, str]:
    """Prefer real Kite bars (pulled via scripts/pull_history.py) when cached;
    fall back to the Yahoo dev loader otherwise."""
    kite = _KITE_CACHE / f"{symbol}_day.pkl"
    if kite.exists():
        return pd.read_pickle(kite), "Kite (real)"
    return load_daily_ohlc(symbol), "Yahoo (dev)"
from kestrel.execution.book import Book
from kestrel.execution.exits import Bar, ExitPlan, OnDataLoss, StopKind, TargetKind
from kestrel.execution.manager import PositionManager
from kestrel.execution.risk import RiskConfig
from kestrel.execution import sizing

SMA_WINDOW = 100          # entry: close above its 100-day average (trend filter)
CAPITAL = 1_000_000.0
RISK_PER_TRADE = 0.01     # risk 1% of equity to the stop (risk-based sizing)


def _plan() -> ExitPlan:
    # 15% trailing stop, 30% target, time-stop at 120 trading-ish days.
    return ExitPlan(
        stop_kind=StopKind.TRAILING,
        stop_pct=0.15,
        target_kind=TargetKind.FIXED,
        target_value=0.30,
        max_holding_days=180,
        on_data_loss=OnDataLoss.FLATTEN,
    )


def run_slice(symbol: str, *, start: str = "2015-01-01") -> dict:
    """Run the slice for one symbol and return a stats dict. Shared by the CLI
    and the local dashboard so both report identical numbers."""
    df, source = _load(symbol)
    df = df[df.index >= start]
    sma = df["close"].rolling(SMA_WINDOW).mean()

    book = Book(cash=CAPITAL)
    pm = PositionManager(book, RiskConfig(max_position_pct=1.0, max_positions=1),
                         slippage_one_way=0.001)

    pending_entry = False   # signal latched on the prior close
    dates = list(df.index)
    for d in dates:
        row = df.loc[d]
        bar = Bar(d.date(), float(row["open"]), float(row["high"]),
                  float(row["low"]), float(row["close"]))

        # 1) fill a pending entry at today's open, sized off the stop distance
        if pending_entry and not book.has(symbol):
            equity = book.equity({symbol: bar.open})
            entry_est = bar.open * 1.001
            stop_est = entry_est * (1 - 0.15)
            qty = sizing.risk_based_size(equity=equity, price=entry_est,
                                         stop_price=stop_est, risk_fraction=RISK_PER_TRADE)
            if qty > 0:
                pm.try_enter(symbol, qty, bar, _plan(), equity=equity)
        pending_entry = False

        # 2) evaluate the exit path against today's bar (incl. the entry day)
        if book.has(symbol):
            pm.on_bar(symbol, bar)

        # 3) latch tomorrow's entry signal from today's close (no look-ahead)
        if not book.has(symbol) and pd.notna(sma.loc[d]) and row["close"] > sma.loc[d]:
            pending_entry = True

    # close any position still open at the end, at the last close, for accounting
    if book.has(symbol):
        last = df.iloc[-1]
        pm.on_bar(symbol, Bar(dates[-1].date(), float(last["open"]), float(last["high"]),
                              float(last["close"]), float(last["close"])), feed_ok=False)

    trades = book.trades
    by_reason: dict[str, int] = {}
    for t in trades:
        by_reason[t.reason] = by_reason.get(t.reason, 0) + 1
    wins = [t for t in trades if t.net_pnl > 0]
    return {
        "symbol": symbol,
        "source": source,
        "start": df.index[0].date().isoformat(),
        "end": df.index[-1].date().isoformat(),
        "trades": len(trades),
        "exit_reasons": by_reason,
        "win_rate": (len(wins) / len(trades)) if trades else 0.0,
        "avg_hold_days": (sum(t.held_days for t in trades) / len(trades)) if trades else 0,
        "gross_pnl": sum(t.gross_pnl for t in trades),
        "costs": sum(t.costs for t in trades),
        "net_pnl": sum(t.net_pnl for t in trades),
        "final_cash": book.cash,
        "capital": CAPITAL,
    }


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    s = run_slice(symbol)
    print(f"\nVertical slice — {s['symbol']}  [{s['source']}], {s['start']} → {s['end']}")
    print(f"Entry: close > {SMA_WINDOW}d SMA (placeholder).  "
          f"Exit: 15% trailing stop / 30% target / 180d time.\n")
    if not s["trades"]:
        print("  no trades")
        return
    print(f"  trades           : {s['trades']}")
    print(f"  exit reasons     : " + ", ".join(f"{k}={v}" for k, v in sorted(s['exit_reasons'].items())))
    print(f"  win rate         : {s['win_rate']:.0%}")
    print(f"  avg hold (days)  : {s['avg_hold_days']:.0f}")
    print(f"  gross P&L        : ₹{s['gross_pnl']:,.0f}")
    print(f"  costs charged    : ₹{s['costs']:,.0f}   ({s['costs']/s['capital']:.2%} of capital)")
    print(f"  net P&L          : ₹{s['net_pnl']:,.0f}")
    print(f"  final cash       : ₹{s['final_cash']:,.0f}")
    print(f"\n  This demonstrates the exit path and cash accounting, not an edge.")
    print(f"  Costs are real (incl. the flat DP charge per sell); exits are all")
    print(f"  code-decided; the book never went cash-negative. (G-28, G-29, D-07)\n")


if __name__ == "__main__":
    main()
