"""Quality / profitability — a fourth documented anomaly (D-17).

The quality (a.k.a. profitability) effect (Novy-Marx 2013; Fama–French 2015's
RMW): profitable, financially sound companies have historically outperformed
unprofitable ones of similar valuation. Return on equity is the canonical,
data-light proxy and the one this factor uses; richer quality (gross margin,
leverage, accruals, earnings stability) needs more fundamental fields than a
single filing carries, and is a natural extension once the ingestion feed
(NSE/BSE XBRL) is populating those fields.

Same contract as momentum / low-vol / value: a factor over point-in-time
inputs, higher score = better. The score is return on equity taken **as of**
each date, so it uses only fundamentals that were public then — the store's
`asof` enforces that. Where ROE is not directly reported, it is approximated by
earnings / book value per share.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from kestrel.data.fundamentals import FundamentalsSource


@dataclass(frozen=True)
class QualityConfig:
    n_hold: int = 10


def _roe(rec) -> float:
    if rec.roe is not None:
        return float(rec.roe)
    if rec.book_value_per_share and rec.book_value_per_share > 0:
        return float(rec.eps_ttm) / float(rec.book_value_per_share)   # ROE ≈ EPS / BVPS
    return float("nan")


def quality_scores(
    prices: pd.DataFrame,
    fundamentals: FundamentalsSource,
    cfg: QualityConfig,
) -> pd.DataFrame:
    """Signal panel: return on equity per symbol per date, point-in-time (only
    fundamentals public by the date are used). Higher = more profitable = better.
    Price is not used in the score (quality is a balance-sheet property), but the
    price panel supplies the date grid and the tradeable set."""
    out = pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    for dt in prices.index:
        d = dt.date()
        for sym in prices.columns:
            if pd.isna(prices.loc[dt, sym]):
                continue
            rec = fundamentals.asof(sym, d)
            if rec is None:
                continue
            out.loc[dt, sym] = _roe(rec)
    return out


def target_holdings(
    scores_row: pd.Series,
    tradeable: list[str],
    cfg: QualityConfig,
) -> set[str]:
    """Equal-weight top-N by quality score (the most profitable names)."""
    eligible = scores_row.reindex(tradeable).dropna()
    if eligible.empty:
        return set()
    return set(eligible.sort_values(ascending=False).head(cfg.n_hold).index)
