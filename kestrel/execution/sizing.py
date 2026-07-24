"""Position sizing (doc 11 G-18, the deliberately-open question).

The docs left sizing blank on purpose — fixed-fractional, volatility-parity,
and risk-based sizing produce very different books from the same signals, and
the right choice interacts with the strategy. This module implements the
candidates as pure, integer-share functions so a backtest can compare them
rather than argue about them, and exposes a `Sizer` protocol so the choice is
configuration, not a hard-coded assumption.

Every function returns a whole number of shares (you cannot buy a fraction on
NSE cash), floors rather than rounds (never size *up* into a cap), and returns
0 when even one share won't fit — so a sizer can always be trusted not to
overspend.

The principled default for a stop-based system is `risk_based_size`: it ties
the position to the ExitPlan's stop so each trade risks the same fraction of
equity, which is what makes a per-trade loss limit meaningful.
"""
from __future__ import annotations

import math
from typing import Protocol


class Sizer(Protocol):
    def __call__(self, *, equity: float, price: float) -> int: ...


def _floor_shares(rupees: float, price: float) -> int:
    if price <= 0 or rupees <= 0:
        return 0
    return int(math.floor(rupees / price))


def equal_weight_size(*, equity: float, price: float, n_slots: int) -> int:
    """Split equity into `n_slots` equal buckets, one position per bucket."""
    if n_slots <= 0:
        return 0
    return _floor_shares(equity / n_slots, price)


def fixed_fractional_size(*, equity: float, price: float, fraction: float) -> int:
    """A fixed `fraction` of equity in each position (e.g. 0.10 = 10%)."""
    if not (0.0 < fraction <= 1.0):
        raise ValueError("fraction must be in (0, 1]")
    return _floor_shares(equity * fraction, price)


def risk_based_size(
    *, equity: float, price: float, stop_price: float, risk_fraction: float
) -> int:
    """Risk a fixed `risk_fraction` of equity on the distance to the stop.

    shares = (risk_fraction * equity) / (entry - stop). This is the sizing that
    makes the per-trade loss limit real: if the stop is hit, the loss is ~the
    budgeted fraction regardless of the stop's width. A tighter stop buys more
    shares, a wider stop fewer — risk, not notional, is held constant.
    """
    if not (0.0 < risk_fraction < 1.0):
        raise ValueError("risk_fraction must be in (0, 1)")
    per_share_risk = price - stop_price
    if per_share_risk <= 0:
        return 0    # stop not below entry — the risk engine will reject anyway
    shares_by_risk = (risk_fraction * equity) / per_share_risk
    # Never let risk sizing exceed what cash can actually buy.
    shares_by_cash = equity / price
    return int(math.floor(min(shares_by_risk, shares_by_cash)))


def vol_target_size(
    *, equity: float, price: float, ann_vol: float, target_vol: float, max_fraction: float = 1.0
) -> int:
    """Volatility-parity: scale the position so its annualised risk contribution
    is `target_vol` of equity. Low-vol names get more, high-vol names less —
    the sizing analogue of the low-volatility factor. Capped at `max_fraction`
    of equity so a near-zero-vol estimate can't demand leverage."""
    if ann_vol <= 0:
        return 0
    fraction = min(target_vol / ann_vol, max_fraction)
    return _floor_shares(equity * fraction, price)
