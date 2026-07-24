"""Point-in-time fundamentals — dated, lagged, look-ahead-safe.

Value and quality factors need per-company fundamentals (earnings, book value,
returns on equity). Two hard truths shape this module:

  * **Kite does not provide fundamentals.** They must come from elsewhere —
    a data vendor, screener.in, or the exchange filings. That source is an
    owner decision (cost, licensing, coverage), so the *real* source is left
    deferred here, exactly as `KiteInstrumentsSource` is inert until auth. What
    is built is the abstraction and a dev source, so the factor math and its
    point-in-time discipline are testable today.

  * **Reporting lag is the value look-ahead trap.** A quarter's earnings are
    not public until weeks after the quarter ends. A backtest that uses them
    from the period-end date is peeking at the future — and it is the single
    most common way a value backtest inflates itself. So a `FundamentalRecord`
    carries an explicit `publish_date`, and `asof(symbol, d)` returns only what
    was **public on or before d**, never merely reported by d.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol, runtime_checkable

# Typical delay between a fiscal period end and the results being public in
# India (SEBI LODR allows ~45 days for quarterly, ~60 for annual). Used only to
# synthesise publish dates when a source gives period-end dates alone; a real
# source should carry the *actual* filing date.
DEFAULT_REPORTING_LAG = timedelta(days=45)


@dataclass(frozen=True)
class FundamentalRecord:
    """One as-of snapshot of a company's fundamentals.

    `period_end` is the fiscal period the numbers describe; `publish_date` is
    when they became public — the only date a point-in-time query may trust.
    Per-share figures so they compose directly with price.
    """
    symbol: str
    period_end: date
    publish_date: date
    eps_ttm: float                 # trailing-twelve-month earnings per share
    book_value_per_share: float
    roe: float | None = None       # return on equity (quality factor input)

    def __post_init__(self) -> None:
        if self.publish_date < self.period_end:
            raise ValueError(
                f"{self.symbol}: publish_date {self.publish_date} precedes "
                f"period_end {self.period_end} — that is look-ahead, not data."
            )


def record_with_lag(
    symbol: str,
    period_end: date,
    eps_ttm: float,
    book_value_per_share: float,
    *,
    roe: float | None = None,
    lag: timedelta = DEFAULT_REPORTING_LAG,
) -> FundamentalRecord:
    """Build a record, synthesising `publish_date = period_end + lag` when the
    true filing date is unknown (dev/backtest convenience only)."""
    return FundamentalRecord(
        symbol=symbol,
        period_end=period_end,
        publish_date=period_end + lag,
        eps_ttm=eps_ttm,
        book_value_per_share=book_value_per_share,
        roe=roe,
    )


@runtime_checkable
class FundamentalsSource(Protocol):
    def asof(self, symbol: str, d: date) -> FundamentalRecord | None:
        """The latest fundamentals for `symbol` that were **public on or before
        d** — never a record whose publish_date is after d."""
        ...


class StaticFundamentals:
    """Development source: an in-memory set of dated records. Runnable and
    testable today; a real point-in-time vendor feed drops in behind the same
    `asof` contract without touching the factor code."""

    def __init__(self, records: list[FundamentalRecord]):
        self._by_symbol: dict[str, list[FundamentalRecord]] = {}
        for r in records:
            self._by_symbol.setdefault(r.symbol, []).append(r)
        for rows in self._by_symbol.values():
            rows.sort(key=lambda r: r.publish_date)

    def asof(self, symbol: str, d: date) -> FundamentalRecord | None:
        rows = self._by_symbol.get(symbol)
        if not rows:
            return None
        public = [r for r in rows if r.publish_date <= d]
        return public[-1] if public else None
