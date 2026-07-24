"""The book — open positions, cash, and a realised-P&L ledger.

Single book, single ledger, single set of positions (D-13, single-user). All
accounting is in rupees. Cash is decremented by (notional + entry cost) on a
fill and credited by (notional − exit cost) on a close, so the cash balance is
always the true fundable figure — the paper account can never spend money it
does not have (the honesty the margin model, G-29, exists to enforce).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from kestrel.execution.exits import ExitPlan


@dataclass
class Position:
    symbol: str
    qty: int                     # shares; LONG (> 0) for the first slice
    entry_price: float           # fill price actually paid (incl. slippage)
    entry_date: date
    plan: ExitPlan
    stop: float                  # live stop (trailing ratchets this up)
    target: float | None
    entry_cost: float            # cash cost charged at entry (for round-trip accounting)

    def notional(self, price: float) -> float:
        return self.qty * price


@dataclass
class Trade:
    """A closed round-trip, kept for the ledger and diagnostics."""
    symbol: str
    qty: int
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    reason: str
    gross_pnl: float             # (exit - entry) * qty
    costs: float                 # entry + exit costs
    net_pnl: float               # gross - costs

    @property
    def held_days(self) -> int:
        return (self.exit_date - self.entry_date).days


@dataclass
class Book:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)

    def has(self, symbol: str) -> bool:
        return symbol in self.positions

    def open_position(self, pos: Position) -> None:
        if self.has(pos.symbol):
            raise ValueError(f"already holding {pos.symbol} — no pyramiding in the slice")
        self.cash -= pos.notional(pos.entry_price) + pos.entry_cost
        self.positions[pos.symbol] = pos

    def close_position(
        self, symbol: str, exit_price: float, exit_date: date, reason: str, exit_cost: float
    ) -> Trade:
        pos = self.positions.pop(symbol)
        self.cash += pos.notional(exit_price) - exit_cost
        gross = (exit_price - pos.entry_price) * pos.qty
        costs = pos.entry_cost + exit_cost
        trade = Trade(
            symbol=symbol,
            qty=pos.qty,
            entry_date=pos.entry_date,
            exit_date=exit_date,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            reason=reason,
            gross_pnl=gross,
            costs=costs,
            net_pnl=gross - costs,
        )
        self.trades.append(trade)
        return trade

    def equity(self, marks: dict[str, float]) -> float:
        """Cash plus the marked-to-market value of open positions. `marks` maps
        symbol → current price; a held symbol missing from `marks` is valued at
        its entry price (no better information)."""
        mtm = sum(
            p.notional(marks.get(sym, p.entry_price)) for sym, p in self.positions.items()
        )
        return self.cash + mtm
