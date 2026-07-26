"""Dividend adjustment for Kite historical bars (G-08).

Kite adjusts historical candles for splits and bonuses only — **not dividends**
(doc 02 §5.1, doc 11 G-08). So every ex-dividend date shows a gap-down that was
never a real loss, and momentum / stop / gap logic reads it as signal. This
module removes that artefact by back-adjusting prices to a total-return basis.

Two honest boundaries:

  * **The math is here; the dividend data is not.** Actual (ex-date, amount)
    events must come from a source Kite does not provide — a vendor, the
    exchange corporate-actions feed, or (for development) Yahoo's dividend
    events. `DividendSource` is that seam, with a dev implementation; a real
    point-in-time source is an owner decision, exactly like fundamentals.

  * **Back-adjustment rewrites history, so keep the raw series too (D-15).**
    The unadjusted candles are the as-of record; the adjusted series is a
    *derived view*. Never overwrite the raw pull with the adjusted one — the
    adjustment factor changes every time a new dividend lands, so a cached
    adjusted series is only correct until the next ex-date.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd


@dataclass(frozen=True)
class DividendEvent:
    symbol: str
    ex_date: date
    amount_per_share: float   # rupees per share, the cash dividend


@runtime_checkable
class DividendSource(Protocol):
    def events(self, symbol: str) -> list[DividendEvent]:
        """All known dividend events for `symbol`, any order."""
        ...


class StaticDividends:
    """Development dividend source: an in-memory list. A real vendor / exchange
    feed drops in behind the same `events` contract. (Yahoo's chart API already
    returns dividend events for dev use — a thin adapter could back this.)"""

    def __init__(self, events: list[DividendEvent]):
        self._by_symbol: dict[str, list[DividendEvent]] = {}
        for e in events:
            self._by_symbol.setdefault(e.symbol, []).append(e)

    def events(self, symbol: str) -> list[DividendEvent]:
        return list(self._by_symbol.get(symbol, []))


def adjust_for_dividends(
    ohlc: pd.DataFrame, events: list[DividendEvent]
) -> pd.DataFrame:
    """Return a copy of `ohlc` back-adjusted for cash dividends (total-return
    basis). Prices *before* each ex-date are scaled down by that dividend's
    yield so the ex-date no longer shows an artificial gap; prices on/after are
    unchanged. Volume is left as-is (dividends do not change share count).

    The reference is the close on the last trading day strictly before the
    ex-date. An event whose ex-date precedes the series (no reference close) is
    skipped. `ohlc` must be date-indexed with an `open/high/low/close` column
    set (extra columns pass through untouched).
    """
    if ohlc.empty or not events:
        return ohlc.copy()

    df = ohlc.copy()
    price_cols = [c for c in ("open", "high", "low", "close") if c in df.columns]
    # cumulative multiplier per bar, starting at 1.0
    factor = pd.Series(1.0, index=df.index)

    # Sum dividends sharing an ex-date FIRST (G-46): two payouts on one ex-date
    # subtract linearly (interim + special = one price drop), not multiplicatively
    # — (ref-d1)/ref * (ref-d2)/ref would over-discount.
    from collections import defaultdict

    per_ex: dict = defaultdict(float)
    for ev in events:
        per_ex[ev.ex_date] += ev.amount_per_share

    for ex_date in sorted(per_ex):
        ex = pd.Timestamp(ex_date)
        before = df.index[df.index < ex]
        if len(before) == 0:
            continue   # ex-date before our history — no reference close
        ref_close = float(df.loc[before[-1], "close"])
        if ref_close <= 0:
            continue
        # clamp: total dividend cannot exceed the price (bad data guard)
        f = max((ref_close - per_ex[ex_date]) / ref_close, 1e-6)
        factor.loc[before] *= f   # all bars strictly before the ex-date

    for c in price_cols:
        df[c] = df[c] * factor
    return df


def adjust_symbol(
    ohlc: pd.DataFrame, symbol: str, source: DividendSource
) -> pd.DataFrame:
    """Convenience: back-adjust `ohlc` using all dividends the source has for
    `symbol`."""
    return adjust_for_dividends(ohlc, source.events(symbol))
