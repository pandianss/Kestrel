"""The backtest engine — deterministic, point-in-time, cost-aware.

Scope (doc 11, G-42): this backtests the **deterministic plane only** — a rule
over historical bars. It does *not* and cannot validate an LLM overlay; that is
forward-tested. Keeping the engine deterministic is deliberate: same inputs →
identical outputs, so a result is reproducible and a change is attributable.

The loop, per rebalance month t:
  1. Ask the universe provider who was tradeable *as of t* (point-in-time).
  2. Realise this month's return of the book chosen *last* month (no
     look-ahead — you cannot earn t's return on a decision made with t's data).
  3. Charge costs on the turnover between last month's book and this month's.
  4. Choose next month's book from the strategy's target holdings.

Returns a `BacktestResult` carrying gross/net series, turnover, and — crucially
— whether the universe was survivorship-biased, so a biased run can never be
silently reported as trustworthy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

import pandas as pd

from kestrel.costs import round_trip_cost_fraction
from kestrel.data.universe import UniverseProvider

# A strategy is: (scores_row, tradeable_symbols) -> set of target symbols.
HoldingsFn = Callable[[pd.Series, list[str]], set]


@dataclass(frozen=True)
class BacktestResult:
    monthly: pd.DataFrame          # columns: gross, net, turnover, n_holdings
    survivorship_biased: bool      # propagated from the universe provider
    min_cross_section: int         # smallest tradeable set seen (diagnostic)

    @property
    def gross(self) -> pd.Series:
        return self.monthly["gross"]

    @property
    def net(self) -> pd.Series:
        return self.monthly["net"]


def run_backtest(
    prices: pd.DataFrame,
    scores: pd.DataFrame,
    universe: UniverseProvider,
    holdings_fn: HoldingsFn,
    *,
    capital: float = 1_000_000.0,
    slippage_one_way: float = 0.0010,
    min_cross_section: int = 20,
) -> BacktestResult:
    """Run the monthly rebalance loop.

    `prices`  — month-end price panel (adjusted close).
    `scores`  — signal panel, same index/columns as `prices` (point-in-time).
    `universe`— point-in-time membership.
    `holdings_fn` — chooses target holdings from (scores_row, tradeable list).
    `capital` — book size, used only to amortise the flat per-scrip DP charge.
    """
    ret = prices.pct_change()
    rows: list[tuple] = []
    prev: set[str] = set()
    smallest = 10**9

    for dt in prices.index:
        d: date = dt.date()
        members = universe.members_asof(d)
        live = prices.loc[dt].dropna().index
        tradeable = [s for s in members if s in live]
        smallest = min(smallest, len(tradeable))

        if len(tradeable) < min_cross_section:
            rows.append((dt, float("nan"), float("nan"), float("nan"), len(prev)))
            continue

        # (2) realise last month's book this month
        if prev:
            gross = float(ret.loc[dt, list(prev)].mean())
            # (3) cost on turnover between prev and new book
            new = holdings_fn(scores.loc[dt], tradeable)
            n = max(len(new), 1)
            turnover = len(new ^ prev) / (2 * n)   # fraction of book replaced
            per_pos_notional = capital / n
            rt = round_trip_cost_fraction(d, per_pos_notional, slippage_one_way)
            cost = turnover * rt
            net = gross - cost
        else:
            new = holdings_fn(scores.loc[dt], tradeable)
            gross = net = float("nan")             # no book held yet
            turnover = 1.0

        rows.append((dt, gross, net, turnover, len(new)))
        prev = new  # (4)

    monthly = pd.DataFrame(
        rows, columns=["dt", "gross", "net", "turnover", "n_holdings"]
    ).set_index("dt")
    return BacktestResult(
        monthly=monthly,
        survivorship_biased=universe.is_survivorship_biased,
        min_cross_section=smallest,
    )
