"""Value — a third documented anomaly (D-17), for the factor comparison.

The value effect (Basu 1977; Fama–French 1992): cheap stocks — high earnings or
book yield relative to price — have historically outperformed expensive ones.
Among the most-replicated anomalies, in India included.

Same contract as momentum and low-vol (higher score = better = cheaper), so the
engine and comparison harness treat all three identically. The one structural
difference is the input: value needs **fundamentals**, and those must be
point-in-time (public as of the scoring date), which is why the score is built
by asking a `FundamentalsSource.asof(symbol, d)` per date — never a single
current snapshot applied backwards (that is the look-ahead trap fundamentals.py
exists to prevent).

Because the real fundamentals source is deferred (an owner data decision, see
fundamentals.py), this factor runs today only on a dev source — its math and
its point-in-time discipline are tested, but a trustworthy value backtest waits
on a real point-in-time fundamentals feed, exactly as the momentum verdict
waits on the point-in-time *universe* (G-43).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from kestrel.data.fundamentals import FundamentalsSource


class ValueMetric(Enum):
    EARNINGS_YIELD = "earnings_yield"     # eps_ttm / price
    BOOK_TO_PRICE = "book_to_price"       # book_value_per_share / price
    BLEND = "blend"                       # mean of the two (equal weight)


@dataclass(frozen=True)
class ValueConfig:
    metric: ValueMetric = ValueMetric.EARNINGS_YIELD
    n_hold: int = 10


def _score_one(rec_eps: float, rec_bvps: float, price: float, metric: ValueMetric) -> float:
    ey = rec_eps / price if price > 0 else float("nan")
    bp = rec_bvps / price if price > 0 else float("nan")
    if metric is ValueMetric.EARNINGS_YIELD:
        return ey
    if metric is ValueMetric.BOOK_TO_PRICE:
        return bp
    return (ey + bp) / 2.0


def value_scores(
    prices: pd.DataFrame,
    fundamentals: FundamentalsSource,
    cfg: ValueConfig,
) -> pd.DataFrame:
    """Signal panel: value score per symbol per date, higher = cheaper = better.

    For each date, each symbol's fundamentals are taken **as of that date**
    (public by then), so the panel is point-in-time by construction. Symbols
    with no public fundamentals yet score NaN and are simply not eligible.
    """
    out = pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    for dt in prices.index:
        d = dt.date()
        row = prices.loc[dt]
        for sym in prices.columns:
            price = row[sym]
            if pd.isna(price):
                continue
            rec = fundamentals.asof(sym, d)
            if rec is None:
                continue
            out.loc[dt, sym] = _score_one(
                rec.eps_ttm, rec.book_value_per_share, float(price), cfg.metric
            )
    return out


def target_holdings(
    scores_row: pd.Series,
    tradeable: list[str],
    cfg: ValueConfig,
) -> set[str]:
    """Equal-weight top-N by value score (the cheapest names), restricted to
    symbols tradeable point-in-time and with a live score."""
    eligible = scores_row.reindex(tradeable).dropna()
    if eligible.empty:
        return set()
    return set(eligible.sort_values(ascending=False).head(cfg.n_hold).index)
