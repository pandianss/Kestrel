"""Universe membership — the abstraction that makes survivorship bias visible.

The 2026-07-23 momentum test proved (doc 11, G-43) that a backtest on *today's*
constituents overstates return by ~18 percentage points a year, because the
universe silently excludes everything that delisted. The fix is point-in-time
membership: at each rebalance, ask "which instruments were tradeable *as of
that date*?" — including ones that no longer exist.

A `UniverseProvider` answers that question. Two implementations:

  * `StaticUniverse` — a fixed ticker list. **Survivorship-biased by
    construction.** Fine for wiring the engine, dangerous for conclusions.
    It says so, loudly, via `is_survivorship_biased`.

  * `PointInTimeUniverse` — backed by dated membership snapshots (the G-43
    Instruments-Loader snapshots). This is the one whose numbers can be
    trusted. Not yet populated — it needs Kite data + the snapshotter.

The engine depends only on the interface, so swapping a real point-in-time
source in later is a constructor change, not a rewrite.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class UniverseProvider(Protocol):
    """Answers: which symbols were members as of a given date."""

    #: True if this provider cannot avoid survivorship bias. The engine
    #: propagates it into results so a biased run can never be mistaken for a
    #: trustworthy one.
    is_survivorship_biased: bool

    def members_asof(self, d: date) -> list[str]:
        ...


class StaticUniverse:
    """A fixed list, applied at every date. Survivorship-biased: the list is
    whatever exists *now*, so anything that delisted is invisible."""

    is_survivorship_biased = True

    def __init__(self, symbols: list[str]):
        self._symbols = list(symbols)

    def members_asof(self, d: date) -> list[str]:
        return list(self._symbols)


class PointInTimeUniverse:
    """Membership from dated snapshots: `snapshots[d]` is the member list as it
    stood on date `d` (forward-filled to the latest snapshot on/before the
    query). Populated from the G-43 Instruments-Loader archive.

    Not survivorship-biased *iff* the snapshots include instruments that later
    delisted — which is the entire reason the snapshotter must run daily from
    Phase 0 and never overwrite (D-15, G-43).
    """

    is_survivorship_biased = False

    def __init__(self, snapshots: dict[date, list[str]]):
        if not snapshots:
            raise ValueError("PointInTimeUniverse needs at least one snapshot")
        self._dates = sorted(snapshots)
        self._snapshots = snapshots

    def members_asof(self, d: date) -> list[str]:
        applicable = [s for s in self._dates if s <= d]
        if not applicable:
            return []
        return list(self._snapshots[applicable[-1]])
