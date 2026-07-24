"""Position Manager (doc 07 §4) — owns every open position, exits without asking.

This is the component D-07 is about: entries are decided upstream, but once a
position is open the Position Manager evaluates its `ExitPlan` every bar and
fires exits deterministically — stop, target, time, or feed-loss — with no
dependency on the cognition plane. It also carries the end-of-day fill model
and drives the book's cash accounting.

Fill model (end-of-day, conservative — doc 07 §4.2):
  * **Entry** fills at the next bar's open, paying up by `slippage_one_way`
    (a buy crosses the spread). Statutory buy costs are charged on top.
  * **Exit** fills at the price the ExitPlan trigger implies (already gap-aware,
    see exits.py). Market-type exits (stop, time, data-loss) pay `slippage`;
    a target is a resting limit and fills at its price. Sell costs — including
    the flat per-scrip DP charge — are charged on top.

Determinism: no wall-clock, no RNG. Given the same bars and config, the book
and ledger are byte-identical (doc 07 §4 "deterministic across the plane").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from kestrel.costs import one_way_cost_fraction, regime_on
from kestrel.execution.book import Book, Position, Trade
from kestrel.execution.exits import (
    Bar,
    ExitPlan,
    ExitReason,
    evaluate_exit,
    initial_stop_price,
    target_price,
    trail_stop,
)
from kestrel.execution.risk import RiskConfig, check_entry

_MARKET_EXITS = {ExitReason.STOP, ExitReason.MAX_HOLDING, ExitReason.DATA_LOSS}


@dataclass(frozen=True)
class EntryResult:
    accepted: bool
    reason: str | None = None
    position: Position | None = None


class PositionManager:
    def __init__(
        self,
        book: Book,
        risk: RiskConfig | None = None,
        *,
        slippage_one_way: float = 0.0010,
    ):
        self.book = book
        self.risk = risk or RiskConfig()
        self.slippage = slippage_one_way
        self.halted = False

    # ---- entries -------------------------------------------------------
    def try_enter(
        self, symbol: str, qty: int, fill_bar: Bar, plan: ExitPlan, *, equity: float
    ) -> EntryResult:
        """Attempt to open `qty` shares of `symbol`, filling at `fill_bar` open.

        Runs the pre-trade risk checks; on rejection nothing touches the book.
        `equity` is passed in (marked at decision time) so sizing/cap checks use
        a consistent figure.
        """
        if qty <= 0:
            return EntryResult(False, "non_positive_qty")
        if self.book.has(symbol):
            return EntryResult(False, "already_held")

        fill_price = fill_bar.open * (1.0 + self.slippage)
        notional = qty * fill_price
        regime = regime_on(fill_bar.d)
        entry_cost = notional * one_way_cost_fraction("buy", regime)

        reason = check_entry(
            cfg=self.risk,
            equity=equity,
            cash=self.book.cash,
            notional=notional,
            entry_cost=entry_cost,
            open_positions=len(self.book.positions),
            halted=self.halted,
        )
        if reason is not None:
            return EntryResult(False, reason)

        stop = initial_stop_price(fill_price, plan)
        tgt = target_price(fill_price, plan)
        pos = Position(
            symbol=symbol,
            qty=qty,
            entry_price=fill_price,
            entry_date=fill_bar.d,
            plan=plan,
            stop=stop,
            target=tgt,
            entry_cost=entry_cost,
        )
        self.book.open_position(pos)
        return EntryResult(True, None, pos)

    # ---- exits ---------------------------------------------------------
    def on_bar(
        self, symbol: str, bar: Bar, *, feed_ok: bool = True
    ) -> Trade | None:
        """Evaluate one open position against one bar. Closes it (returning the
        Trade) if an exit triggers, else trails the stop and holds.

        Exits are never gated by the risk engine — reducing exposure is always
        allowed, including when halted."""
        pos = self.book.positions.get(symbol)
        if pos is None:
            return None

        signal = evaluate_exit(
            stop=pos.stop,
            target=pos.target,
            entry_date=pos.entry_date,
            plan=pos.plan,
            bar=bar,
            feed_ok=feed_ok,
        )
        if signal is None:
            # No exit — ratchet a trailing stop for next bar and hold.
            pos.stop = trail_stop(pos.stop, pos.entry_price, pos.plan, bar.close)
            return None

        exit_price = signal.price
        if signal.reason in _MARKET_EXITS:
            exit_price *= (1.0 - self.slippage)   # market sell gives up slippage
        regime = regime_on(bar.d)
        notional = pos.qty * exit_price
        exit_cost = (
            notional * one_way_cost_fraction("sell", regime)
            + regime.dp_charge_per_sell_scrip
        )
        return self.book.close_position(
            symbol, exit_price, bar.d, signal.reason.value, exit_cost
        )

    def trip_kill_switch(self) -> None:
        """Halt new entries. Exits continue (they never consult risk)."""
        self.halted = True

    def reset_kill_switch(self) -> None:
        self.halted = False
