"""Cross-sectional momentum — the first documented anomaly (D-17).

Jegadeesh & Titman (1993): rank by trailing return over a lookback window,
*skipping the most recent month* to avoid short-term reversal, then hold the
top names. Roughly three decades of out-of-sample replication across markets,
including India on broad universes.

The strategy is a pure function of a price panel: it returns, for each
rebalance date, the target holdings. It knows nothing about costs, execution,
or the universe source — those are the engine's job. That separation is what
lets the same factor run in a backtest and, later, feed the live screener.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class MomentumConfig:
    lookback_months: int = 12   # J&T standard: 12-month formation
    skip_months: int = 1        # skip the most recent month (reversal)
    n_hold: int = 10            # equal-weight top-N


def momentum_scores(prices: pd.DataFrame, cfg: MomentumConfig) -> pd.DataFrame:
    """Signal panel: return from t-lookback to t-skip, per symbol per date.
    Uses only information available *at* each date (shifted appropriately), so
    the signal is point-in-time by construction — no look-ahead."""
    return prices.shift(cfg.skip_months) / prices.shift(cfg.lookback_months) - 1


def target_holdings(
    scores_row: pd.Series,
    tradeable: list[str],
    cfg: MomentumConfig,
) -> set[str]:
    """The equal-weight top-N by score, restricted to symbols that were
    tradeable (point-in-time universe ∩ has a live price)."""
    eligible = scores_row.reindex(tradeable).dropna()
    if eligible.empty:
        return set()
    return set(eligible.sort_values(ascending=False).head(cfg.n_hold).index)
