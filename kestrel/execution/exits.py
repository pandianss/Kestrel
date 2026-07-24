"""Deterministic exit rules (doc 07 §2.1) evaluated on daily bars.

This is the heart of D-07: exits never depend on an LLM. An `ExitPlan` is
mandatory on every entry (the risk engine rejects an entry without one), and
once a trigger is hit the exit fires regardless of what any upstream model
thinks. The evaluation is a pure function of (position state, bar) — no
wall-clock, no RNG — so a backtest is byte-reproducible (doc 07 §4).

Conservative by construction (doc 07 §4.2, "default pessimistic"):

  * **Gap-through is modelled honestly.** A long stop at S fills at
    `min(open, S)` — if the bar gaps below the stop, you fill at the (worse)
    open, not at the stop you never got. You cannot exit at a price the market
    jumped past.
  * **Favourable gaps are not banked.** A target fills at the target price,
    never at a better gap-up open — we do not credit luck we cannot rely on.
  * **Stop wins ties.** If a single bar's range spans both stop and target,
    OHLC cannot say which came first, so we assume the stop did — the worse
    outcome.

LONG-only for the first slice (documented long-only anomalies, D-17). The
`sign` hook is where short support slots in later.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class StopKind(Enum):
    FIXED = "FIXED"
    TRAILING = "TRAILING"   # ratchets up on new highs, never down


class TargetKind(Enum):
    FIXED = "FIXED"
    R_MULTIPLE = "R_MULTIPLE"   # multiple of initial risk (entry - stop)


class ExitReason(Enum):
    STOP = "stop"
    TARGET = "target"
    MAX_HOLDING = "max_holding"
    DATA_LOSS = "data_loss"     # on_data_loss = FLATTEN (doc 07 §3.2)


class OnDataLoss(Enum):
    FLATTEN = "FLATTEN"
    HOLD = "HOLD"


@dataclass(frozen=True)
class Bar:
    """One daily OHLC bar. `close` is the adjusted close used elsewhere."""
    d: date
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class ExitPlan:
    """Matches doc 07 §2.1. `stop_pct`/`target` are expressed relative to the
    entry so a plan is independent of the fill price until the position opens."""
    stop_kind: StopKind
    stop_pct: float                       # fractional distance below entry, e.g. 0.08
    target_kind: TargetKind | None = None
    target_value: float | None = None     # FIXED: fractional above entry; R_MULTIPLE: multiple of risk
    max_holding_days: int | None = None
    on_data_loss: OnDataLoss = OnDataLoss.FLATTEN

    def __post_init__(self) -> None:
        if not (0.0 < self.stop_pct < 1.0):
            raise ValueError("stop_pct must be a fraction in (0, 1)")
        if self.target_kind is not None and self.target_value is None:
            raise ValueError("target_kind set but target_value is None")


@dataclass(frozen=True)
class ExitSignal:
    reason: ExitReason
    price: float


def initial_stop_price(entry: float, plan: ExitPlan) -> float:
    """The stop price at entry — the reference the risk engine sanity-checks
    and trailing later ratchets up from."""
    return entry * (1.0 - plan.stop_pct)


def target_price(entry: float, plan: ExitPlan) -> float | None:
    if plan.target_kind is None:
        return None
    if plan.target_kind is TargetKind.FIXED:
        return entry * (1.0 + plan.target_value)
    # R_MULTIPLE: target = entry + value * (entry - stop)
    risk = entry - initial_stop_price(entry, plan)
    return entry + plan.target_value * risk


def trail_stop(current_stop: float, entry: float, plan: ExitPlan, bar_close: float) -> float:
    """Ratchet a trailing stop upward off the latest close; never loosen it.
    A FIXED stop is returned unchanged."""
    if plan.stop_kind is not StopKind.TRAILING:
        return current_stop
    candidate = bar_close * (1.0 - plan.stop_pct)
    return max(current_stop, candidate)


def evaluate_exit(
    *,
    stop: float,
    target: float | None,
    entry_date: date,
    plan: ExitPlan,
    bar: Bar,
    feed_ok: bool = True,
) -> ExitSignal | None:
    """Decide whether a LONG position exits on this bar, and at what price.

    Precedence (worst-first, all deterministic):
      1. data loss with FLATTEN  → exit at open
      2. stop (incl. gap-through) → min(open, stop)
      3. target                  → target price (favourable gap not banked)
      4. max_holding reached      → close
    Stop is checked before target so a bar spanning both resolves pessimistically.
    """
    if not feed_ok and plan.on_data_loss is OnDataLoss.FLATTEN:
        return ExitSignal(ExitReason.DATA_LOSS, bar.open)

    # Stop: triggered if the bar trades at or below it (low <= stop) OR gaps below.
    if bar.low <= stop:
        fill = min(bar.open, stop)   # gap-through fills at the worse open
        return ExitSignal(ExitReason.STOP, fill)

    # Target: triggered if the bar trades at or above it.
    if target is not None and bar.high >= target:
        return ExitSignal(ExitReason.TARGET, target)   # never credit a gap-up open

    # Time exit: holding age is counted in bars elapsed since entry.
    if plan.max_holding_days is not None:
        held = (bar.d - entry_date).days
        if held >= plan.max_holding_days:
            return ExitSignal(ExitReason.MAX_HOLDING, bar.close)

    return None
