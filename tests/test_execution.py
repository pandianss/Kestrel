"""Tests for the execution plane — deterministic exits, honest fills, cash.

The properties under test are the ones that make a paper backtest trustworthy:
gap-through is modelled as a loss not a fill-at-stop, favourable gaps are not
banked, the stop wins an intrabar tie, cash can never go where it can't, and
the same bars produce an identical ledger.
"""
from datetime import date

import pytest

from kestrel.execution.book import Book, Position
from kestrel.execution.exits import (
    Bar,
    ExitPlan,
    ExitReason,
    OnDataLoss,
    StopKind,
    TargetKind,
    evaluate_exit,
    initial_stop_price,
    target_price,
    trail_stop,
)
from kestrel.execution.manager import PositionManager
from kestrel.execution.risk import RiskConfig, check_entry
from kestrel.execution import sizing


def _plan(stop_pct=0.10, target=None, tkind=None, max_hold=None, dl=OnDataLoss.FLATTEN):
    return ExitPlan(
        stop_kind=StopKind.FIXED,
        stop_pct=stop_pct,
        target_kind=tkind,
        target_value=target,
        max_holding_days=max_hold,
        on_data_loss=dl,
    )


D0 = date(2024, 1, 1)
D1 = date(2024, 1, 2)


# ---- exits: the conservative fill rules ---------------------------------

def test_stop_intrabar_fills_at_stop():
    # entry 100, stop 90. Bar dips to 88 but opens at 95 -> filled at the stop.
    sig = evaluate_exit(stop=90, target=None, entry_date=D0, plan=_plan(),
                        bar=Bar(D1, open=95, high=97, low=88, close=94))
    assert sig.reason is ExitReason.STOP and sig.price == 90


def test_stop_gap_through_fills_at_open_not_stop():
    # Gap down: opens at 85, below the 90 stop. You cannot exit at 90 you jumped
    # past — fill at the worse open.
    sig = evaluate_exit(stop=90, target=None, entry_date=D0, plan=_plan(),
                        bar=Bar(D1, open=85, high=86, low=83, close=84))
    assert sig.reason is ExitReason.STOP and sig.price == 85


def test_target_fills_at_target_not_favourable_gap():
    # Gap up through a 110 target; we do NOT bank the 115 open.
    sig = evaluate_exit(stop=90, target=110, entry_date=D0, plan=_plan(target=0.10, tkind=TargetKind.FIXED),
                        bar=Bar(D1, open=115, high=118, low=114, close=116))
    assert sig.reason is ExitReason.TARGET and sig.price == 110


def test_stop_wins_intrabar_tie():
    # Bar spans BOTH stop (90) and target (110). OHLC can't say which first ->
    # assume the stop (pessimistic).
    sig = evaluate_exit(stop=90, target=110, entry_date=D0, plan=_plan(target=0.10, tkind=TargetKind.FIXED),
                        bar=Bar(D1, open=100, high=112, low=88, close=105))
    assert sig.reason is ExitReason.STOP


def test_max_holding_exits_at_close():
    plan = _plan(max_hold=5)
    bar = Bar(date(2024, 1, 8), open=101, high=103, low=99, close=102)  # 7 days later
    sig = evaluate_exit(stop=90, target=None, entry_date=D0, plan=plan, bar=bar)
    assert sig.reason is ExitReason.MAX_HOLDING and sig.price == 102


def test_no_exit_when_nothing_triggers():
    sig = evaluate_exit(stop=90, target=110, entry_date=D0, plan=_plan(target=0.10, tkind=TargetKind.FIXED),
                        bar=Bar(D1, open=100, high=105, low=96, close=101))
    assert sig is None


def test_data_loss_flatten_exits_at_open():
    sig = evaluate_exit(stop=90, target=None, entry_date=D0, plan=_plan(dl=OnDataLoss.FLATTEN),
                        bar=Bar(D1, open=99, high=100, low=98, close=99), feed_ok=False)
    assert sig.reason is ExitReason.DATA_LOSS and sig.price == 99


def test_data_loss_hold_does_not_exit():
    sig = evaluate_exit(stop=90, target=None, entry_date=D0, plan=_plan(dl=OnDataLoss.HOLD),
                        bar=Bar(D1, open=99, high=100, low=98, close=99), feed_ok=False)
    assert sig is None


def test_trailing_stop_ratchets_up_only():
    plan = ExitPlan(stop_kind=StopKind.TRAILING, stop_pct=0.10)
    s0 = initial_stop_price(100, plan)          # 90
    s1 = trail_stop(s0, 100, plan, bar_close=120)   # 120*0.9 = 108 -> up
    assert s1 == pytest.approx(108)
    s2 = trail_stop(s1, 100, plan, bar_close=110)   # 110*0.9 = 99 < 108 -> hold
    assert s2 == pytest.approx(108)


def test_r_multiple_target():
    plan = _plan(stop_pct=0.10, target=2.0, tkind=TargetKind.R_MULTIPLE)
    # entry 100, stop 90, risk 10, 2R target = 120
    assert target_price(100, plan) == pytest.approx(120)


# ---- book: cash accounting ----------------------------------------------

def test_open_decrements_cash_close_credits_and_records_pnl():
    book = Book(cash=100_000)
    pos = Position("X", qty=100, entry_price=100.0, entry_date=D0, plan=_plan(),
                   stop=90, target=None, entry_cost=50.0)
    book.open_position(pos)
    assert book.cash == pytest.approx(100_000 - 100 * 100 - 50)   # notional + cost

    trade = book.close_position("X", exit_price=110.0, exit_date=D1, reason="target", exit_cost=30.0)
    assert trade.gross_pnl == pytest.approx((110 - 100) * 100)
    assert trade.net_pnl == pytest.approx(1000 - (50 + 30))
    assert book.cash == pytest.approx(100_000 - 10_000 - 50 + 11_000 - 30)


def test_no_pyramiding():
    book = Book(cash=100_000)
    pos = Position("X", 100, 100.0, D0, _plan(), 90, None, 0.0)
    book.open_position(pos)
    with pytest.raises(ValueError):
        book.open_position(Position("X", 10, 100.0, D0, _plan(), 90, None, 0.0))


def test_equity_marks_to_market():
    book = Book(cash=50_000)
    book.open_position(Position("X", 100, 100.0, D0, _plan(), 90, None, 0.0))
    # cash now 40_000; mark X at 120 -> +12_000
    assert book.equity({"X": 120.0}) == pytest.approx(40_000 + 12_000)


# ---- sizing --------------------------------------------------------------

def test_risk_based_size_ties_to_stop_distance():
    # risk 1% of 1,000,000 = 10,000; stop distance 100-90 = 10 -> 1000 shares
    n = sizing.risk_based_size(equity=1_000_000, price=100, stop_price=90, risk_fraction=0.01)
    assert n == 1000


def test_risk_based_size_capped_by_cash():
    # tiny stop distance would demand huge size; cash caps it at equity/price
    n = sizing.risk_based_size(equity=100_000, price=100, stop_price=99.9, risk_fraction=0.10)
    assert n == 1000   # 100_000 / 100


def test_sizing_floors_never_rounds_up():
    assert sizing.fixed_fractional_size(equity=10_000, price=300, fraction=0.10) == 3  # 1000/300


def test_sizing_zero_when_unaffordable():
    assert sizing.equal_weight_size(equity=100, price=500, n_slots=10) == 0


def test_vol_target_inverse_to_vol():
    lo = sizing.vol_target_size(equity=1_000_000, price=100, ann_vol=0.10, target_vol=0.10)
    hi = sizing.vol_target_size(equity=1_000_000, price=100, ann_vol=0.40, target_vol=0.10)
    assert lo > hi   # calmer name gets a bigger position


# ---- risk engine ---------------------------------------------------------

def test_risk_blocks_insufficient_cash():
    cfg = RiskConfig(max_position_pct=1.0)
    r = check_entry(cfg=cfg, equity=100_000, cash=5_000, notional=10_000,
                    entry_cost=10, open_positions=0, halted=False)
    assert r == "insufficient_cash"


def test_risk_blocks_per_instrument_cap():
    cfg = RiskConfig(max_position_pct=0.20)
    r = check_entry(cfg=cfg, equity=100_000, cash=100_000, notional=25_000,
                    entry_cost=10, open_positions=0, halted=False)
    assert r == "per_instrument_cap"


def test_risk_blocks_when_halted():
    r = check_entry(cfg=RiskConfig(), equity=100_000, cash=100_000, notional=1_000,
                    entry_cost=1, open_positions=0, halted=True)
    assert r == "kill_switch_halted"


def test_risk_blocks_max_positions():
    cfg = RiskConfig(max_positions=3)
    r = check_entry(cfg=cfg, equity=100_000, cash=100_000, notional=1_000,
                    entry_cost=1, open_positions=3, halted=False)
    assert r == "max_positions_reached"


# ---- manager: integration ------------------------------------------------

def test_entry_fills_at_open_plus_slippage_and_charges_cost():
    book = Book(cash=1_000_000)
    pm = PositionManager(book, RiskConfig(max_position_pct=1.0), slippage_one_way=0.001)
    bar = Bar(D0, open=100, high=101, low=99, close=100)
    res = pm.try_enter("X", qty=100, fill_bar=bar, plan=_plan(), equity=1_000_000)
    assert res.accepted
    assert res.position.entry_price == pytest.approx(100 * 1.001)   # paid up
    assert book.cash < 1_000_000 - 100 * 100.1                      # plus buy cost


def test_rejected_entry_leaves_book_untouched():
    # equity roomy (per-instrument cap OK) but cash short -> isolates the cash check
    book = Book(cash=1_000)
    pm = PositionManager(book, RiskConfig(max_position_pct=1.0))
    bar = Bar(D0, open=100, high=101, low=99, close=100)
    res = pm.try_enter("X", qty=100, fill_bar=bar, plan=_plan(), equity=1_000_000)
    assert not res.accepted and res.reason == "insufficient_cash"
    assert book.cash == 1_000 and not book.positions


def test_stop_exit_closes_with_sell_cost_and_dp_charge():
    book = Book(cash=1_000_000)
    pm = PositionManager(book, RiskConfig(max_position_pct=1.0), slippage_one_way=0.0)
    pm.try_enter("X", 100, Bar(D0, 100, 100, 100, 100), _plan(stop_pct=0.10), equity=1_000_000)
    # next bar hits the stop at 90
    trade = pm.on_bar("X", Bar(D1, open=95, high=96, low=88, close=92))
    assert trade is not None and trade.reason == "stop"
    assert trade.exit_price == pytest.approx(90)     # intrabar stop, no slippage
    assert trade.costs > 0                            # includes the flat DP charge
    assert "X" not in book.positions


def test_exit_fires_even_when_halted():
    book = Book(cash=1_000_000)
    pm = PositionManager(book, RiskConfig(max_position_pct=1.0), slippage_one_way=0.0)
    pm.try_enter("X", 100, Bar(D0, 100, 100, 100, 100), _plan(), equity=1_000_000)
    pm.trip_kill_switch()
    trade = pm.on_bar("X", Bar(D1, open=95, high=96, low=88, close=92))
    assert trade is not None    # halt blocks entries, never exits


def _run(seed_bars):
    book = Book(cash=1_000_000)
    pm = PositionManager(book, RiskConfig(max_position_pct=1.0), slippage_one_way=0.001)
    pm.try_enter("X", 100, seed_bars[0], _plan(stop_pct=0.10, target=0.20, tkind=TargetKind.FIXED),
                 equity=1_000_000)
    for b in seed_bars[1:]:
        pm.on_bar("X", b)
    return book


def test_determinism_same_bars_identical_ledger():
    bars = [
        Bar(D0, 100, 100, 100, 100),
        Bar(D1, 101, 103, 100, 102),
        Bar(date(2024, 1, 3), 102, 125, 101, 124),   # hits 120 target
    ]
    a = _run(bars)
    b = _run(bars)
    assert [t.net_pnl for t in a.trades] == [t.net_pnl for t in b.trades]
    assert a.cash == b.cash
    assert len(a.trades) == 1 and a.trades[0].reason == "target"
