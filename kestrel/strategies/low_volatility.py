"""Low-volatility — a second documented anomaly (D-17), for comparison.

The low-volatility effect (Haugen & Baker 1991; Blitz & van Vliet 2007;
Baker–Bradley–Wurgler 2011): low-risk stocks have historically earned returns
as high as or higher than high-risk stocks, inverting the textbook risk–return
line. Replicated across markets and decades, including India. Its practical
appeal for a positional book is shallower drawdowns, not just the anomaly.

It exists here so the eventual point-in-time test has something to compare
momentum *against*. The two factors are deliberately different in character —
momentum chases trend, low-vol avoids risk — and they are often weakly or
negatively correlated, so "which is real on our universe" is a meaningful
question rather than two views of the same thing.

Same contract as momentum (`kestrel/strategies/momentum.py`): a pure function
of a price panel, returning target holdings per rebalance date. Higher score =
better, so the engine and `target_holdings` treat both factors identically —
here the score is *negative* realized volatility (less vol → higher score).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class LowVolConfig:
    lookback_months: int = 12   # window for realized volatility
    min_months: int = 6         # need at least this much history to score
    n_hold: int = 10            # equal-weight lowest-vol N


def lowvol_scores(prices: pd.DataFrame, cfg: LowVolConfig) -> pd.DataFrame:
    """Signal panel: **negative** trailing realized volatility of monthly
    returns, per symbol per date. Higher (closer to zero) = lower risk = better.

    Point-in-time by construction: the volatility at date t uses only returns
    realized up to and including t, all knowable at t — no look-ahead. Unlike
    momentum there is no skip month; short-term reversal is not the concern for
    a variance estimate.
    """
    returns = prices.pct_change()
    vol = returns.rolling(cfg.lookback_months, min_periods=cfg.min_months).std()
    return -vol


def target_holdings(
    scores_row: pd.Series,
    tradeable: list[str],
    cfg: LowVolConfig,
) -> set[str]:
    """Equal-weight top-N by score (i.e. the lowest-volatility names),
    restricted to symbols tradeable point-in-time and with a live signal."""
    eligible = scores_row.reindex(tradeable).dropna()
    if eligible.empty:
        return set()
    return set(eligible.sort_values(ascending=False).head(cfg.n_hold).index)
