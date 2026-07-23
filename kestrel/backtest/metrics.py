"""Performance metrics for a monthly return series.

Deliberately includes the *honest* statistics — t-stat and information ratio —
not just CAGR. The 2026-07-23 momentum test showed a 26% CAGR that was almost
entirely survivorship bias; the t-stat is what exposed it (doc 11, G-01/G-43).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

MONTHS_PER_YEAR = 12


@dataclass(frozen=True)
class PerfStats:
    months: int
    cagr: float
    vol_annual: float
    sharpe: float
    max_drawdown: float
    t_stat: float           # of the mean monthly return vs zero

    def __str__(self) -> str:
        return (
            f"n={self.months:>4}  CAGR={self.cagr:+7.1%}  vol={self.vol_annual:6.1%}  "
            f"Sharpe={self.sharpe:5.2f}  maxDD={self.max_drawdown:7.1%}  t={self.t_stat:5.2f}"
        )


def perf_stats(monthly_returns: pd.Series) -> PerfStats | None:
    """Compute stats from a series of monthly simple returns. Returns None if
    the sample is too short to mean anything (<24 months)."""
    r = monthly_returns.dropna()
    if len(r) < 24:
        return None
    n = len(r)
    years = n / MONTHS_PER_YEAR
    cagr = float((1 + r).prod() ** (1 / years) - 1)
    mu, sigma = float(r.mean()), float(r.std(ddof=1))
    vol_annual = sigma * math.sqrt(MONTHS_PER_YEAR)
    sharpe = (mu * MONTHS_PER_YEAR) / vol_annual if vol_annual > 0 else 0.0
    equity = (1 + r).cumprod()
    max_dd = float((equity / equity.cummax() - 1).min())
    t_stat = (mu / (sigma / math.sqrt(n))) if sigma > 0 else 0.0
    return PerfStats(n, cagr, vol_annual, sharpe, max_dd, t_stat)


def information_ratio(strategy: pd.Series, benchmark: pd.Series) -> tuple[float, float]:
    """Annualised active return and information ratio of `strategy` over
    `benchmark`, on their common months. This is *the control that matters*
    when the universe is survivorship-biased: measured against the same pool,
    it isolates the factor's marginal contribution."""
    a, b = strategy.dropna().align(benchmark.dropna(), join="inner")
    excess = (a - b).dropna()
    if len(excess) < 24:
        return float("nan"), float("nan")
    te = excess.std(ddof=1) * math.sqrt(MONTHS_PER_YEAR)
    ann = float(excess.mean() * MONTHS_PER_YEAR)
    ir = ann / te if te > 0 else 0.0
    return ann, ir
