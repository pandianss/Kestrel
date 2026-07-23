"""Tests for the Indian cost model — the money-losing-if-wrong number.

These encode the four traps from doc 07 §5.1 as assertions, so a future edit
that flattens STT or drops the DP charge fails loudly.
"""
from datetime import date

from kestrel.costs import one_way_cost_fraction, regime_on, round_trip_cost_fraction


def test_stt_is_asymmetric_buy_vs_sell():
    r = regime_on(date(2026, 1, 1))
    buy = one_way_cost_fraction("buy", r)
    sell = one_way_cost_fraction("sell", r)
    # Buy carries stamp duty; sell does not. So buy > sell for delivery,
    # even though STT is symmetric for delivery. Trap: they are NOT equal.
    assert buy != sell
    assert buy > sell


def test_zero_brokerage_is_not_zero_cost():
    r = regime_on(date(2026, 1, 1))
    assert r.brokerage_delivery == 0.0
    # Despite zero brokerage, a round trip still costs real money.
    rt = round_trip_cost_fraction(date(2026, 1, 1), notional_per_position=100_000)
    assert rt > 0.002  # at least STT both sides


def test_dp_charge_hits_small_positions_harder():
    """The flat per-scrip DP charge is a larger fraction of a small position —
    doc 07 §5.1 trap 3. A Rs 10k position pays proportionally more than Rs 1L."""
    small = round_trip_cost_fraction(date(2026, 1, 1), notional_per_position=10_000)
    large = round_trip_cost_fraction(date(2026, 1, 1), notional_per_position=1_000_000)
    assert small > large


def test_round_trip_is_a_plausible_magnitude():
    # For a liquid large cap at Rs 1L, round trip should land in a sane band:
    # ~0.2% STT + ~0.015% stamp + tiny exchange/GST + 0.20% slippage ≈ 0.4-0.5%.
    rt = round_trip_cost_fraction(date(2026, 1, 1), notional_per_position=100_000)
    assert 0.003 < rt < 0.007


def test_regime_selection_is_date_aware():
    r = regime_on(date(2026, 7, 1))
    assert r.effective_from <= date(2026, 7, 1)
