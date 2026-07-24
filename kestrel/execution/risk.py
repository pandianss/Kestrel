"""Deterministic pre-trade risk engine (doc 07 §3), slice subset.

Every entry passes these hard checks *before* any fill. The rule that matters
most (doc 07 §3): **risk checks never block an exit.** Reducing exposure is
unconditionally permitted — this module only ever gates ENTRIES. Exits run
through the Position Manager without consulting it.

Scope here is what is locally computable for an end-of-day cash (CNC) book:
exit-plan presence (enforced by the type system upstream), full-cash margin
(delivery needs the whole notional — no leverage), a per-instrument cap, and a
position-count cap. The F&O SPAN margin model (G-29) is a live-phase concern;
CNC delivery margin is simply "do you have the cash", which is the honest model
for the positional design (D-16).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    max_position_pct: float = 0.20     # a single name ≤ 20% of equity
    max_positions: int = 10            # book breadth (pairs with n_hold)
    cash_safety_factor: float = 1.0    # CNC delivery: need the full cash

    def __post_init__(self) -> None:
        if not (0.0 < self.max_position_pct <= 1.0):
            raise ValueError("max_position_pct must be in (0, 1]")
        if self.max_positions <= 0:
            raise ValueError("max_positions must be positive")


def check_entry(
    *,
    cfg: RiskConfig,
    equity: float,
    cash: float,
    notional: float,
    entry_cost: float,
    open_positions: int,
    halted: bool,
) -> str | None:
    """Return None if the entry is allowed, else a machine-readable reason.

    `halted` is the kill-switch state (daily-loss breach, data outage, manual);
    when set, no new entries — but exits are unaffected because they never call
    this function.
    """
    if halted:
        return "kill_switch_halted"
    if open_positions >= cfg.max_positions:
        return "max_positions_reached"
    if notional > cfg.max_position_pct * equity:
        return "per_instrument_cap"
    if notional + entry_cost > cash * cfg.cash_safety_factor:
        return "insufficient_cash"
    return None
