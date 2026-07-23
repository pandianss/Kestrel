"""Indian transaction-cost model — the money-losing-if-wrong number.

Rates sourced from Zerodha's charges page and archived in
`regulatory/zerodha/zerodha-charges_2026-07-22.md`; specified in doc 07 §5.1.

Per D-15, cost rates live in a **dated, versioned** structure with the source
recorded, so a backtest over 2020 can be re-run under the cost regime that
applied then. `COST_REGIMES` is that structure; `cost_model()` selects the
regime in force on a given date.

The design (doc 07 §5.1) flags four traps this encodes explicitly:
  1. STT is asymmetric — different by segment and by buy vs sell.
  2. Options brokerage is flat Rs 20, not a percentage (not modelled here —
     the positional design D-16 trades CNC delivery, not options).
  3. DP charges are per-scrip on the sell, not per-trade.
  4. "Zero brokerage" delivery is not zero cost — STT/stamp/exchange/GST/DP
     all still apply.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CostRegime:
    """A dated snapshot of the charge schedule. All rates are fractions
    (0.001 == 0.1%), except flat per-order/per-scrip amounts in rupees."""

    effective_from: date
    source: str
    # Equity delivery (CNC) — the segment the positional design trades.
    brokerage_delivery: float          # fraction of turnover (Zerodha: 0)
    stt_buy: float                     # fraction, buy side
    stt_sell: float                    # fraction, sell side
    exchange_txn_nse: float            # fraction, per side
    sebi_turnover: float               # fraction, per side
    stamp_duty_buy: float              # fraction, buy side only
    gst_rate: float                    # on (brokerage + exchange_txn + sebi)
    dp_charge_per_sell_scrip: float    # flat rupees, per scrip on delivery sell


# Verified 2026-07-22 against zerodha.com/charges (archived).
# dp_charge is Rs 15.34/scrip on the sell; encoded as a flat amount and
# applied per position exited, not as a fraction of turnover.
COST_REGIMES: list[CostRegime] = [
    CostRegime(
        effective_from=date(2025, 2, 8),   # post the Feb-2025 charge revision
        source="zerodha.com/charges, archived 2026-07-22 (doc 07 §5.1)",
        brokerage_delivery=0.0,
        stt_buy=0.001,                     # 0.1%
        stt_sell=0.001,                    # 0.1%
        exchange_txn_nse=0.0000297,        # 0.00297% NSE equity
        sebi_turnover=0.000001,            # Rs 10 / crore
        stamp_duty_buy=0.00015,            # 0.015%, buy side
        gst_rate=0.18,
        dp_charge_per_sell_scrip=15.34,
    ),
]


def regime_on(d: date) -> CostRegime:
    """The cost regime in force on date `d` (latest effective_from <= d)."""
    applicable = [r for r in COST_REGIMES if r.effective_from <= d]
    if not applicable:
        # Before our earliest dated regime: use the earliest, but a caller
        # backtesting pre-2025 should add the historical regime rather than
        # silently trust today's rates.
        return min(COST_REGIMES, key=lambda r: r.effective_from)
    return max(applicable, key=lambda r: r.effective_from)


def one_way_cost_fraction(side: str, regime: CostRegime) -> float:
    """Percentage-based cost of one leg (buy or sell), as a fraction of that
    leg's notional. Excludes the flat DP charge (added per-scrip in
    `round_trip_cost`). `side` is 'buy' or 'sell'."""
    if side == "buy":
        stt = regime.stt_buy
        stamp = regime.stamp_duty_buy
    elif side == "sell":
        stt = regime.stt_sell
        stamp = 0.0
    else:
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    taxable = regime.brokerage_delivery + regime.exchange_txn_nse + regime.sebi_turnover
    gst = regime.gst_rate * taxable
    return (
        regime.brokerage_delivery
        + stt
        + regime.exchange_txn_nse
        + regime.sebi_turnover
        + stamp
        + gst
    )


def round_trip_cost_fraction(
    d: date,
    notional_per_position: float,
    slippage_one_way: float = 0.0010,
) -> float:
    """Total round-trip cost (buy + hold + sell) for one position, expressed
    as a fraction of the position's notional.

    Includes the per-scrip DP charge on the sell, amortised over the position
    notional — which is why small positions are proportionally more expensive
    (doc 07 §5.1 trap 3).

    `slippage_one_way`: modelled market-impact/spread cost per leg. Default
    0.10% per side (0.20% round trip) for liquid large caps — deliberately a
    starting assumption to be fitted against replayed fills (G-09), and biased
    to the conservative side per doc 07 §4.2.
    """
    r = regime_on(d)
    pct = one_way_cost_fraction("buy", r) + one_way_cost_fraction("sell", r)
    pct += 2 * slippage_one_way
    dp = r.dp_charge_per_sell_scrip / notional_per_position if notional_per_position > 0 else 0.0
    return pct + dp
