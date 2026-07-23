"""Bridge: archived reference snapshots -> point-in-time universe.

Closes the loop the 2026-07-23 finding demanded. The snapshotter (G-43)
captures dated, immutable instruments snapshots; this reads them back as
point-in-time membership and hands the engine a `PointInTimeUniverse` whose
numbers can be trusted — *because* it includes whatever was tradeable on each
date, not just today's survivors.
"""
from __future__ import annotations

import csv
import io

from kestrel.data.snapshot import SnapshotStore
from kestrel.data.universe import PointInTimeUniverse


def build_pit_universe(
    store: SnapshotStore,
    *,
    dataset: str = "instruments",
    symbol_col: str = "tradingsymbol",
) -> PointInTimeUniverse:
    """Read every instruments snapshot in `store` into dated membership and
    return a PointInTimeUniverse. Each snapshot date contributes the set of
    symbols tradeable as of that date."""
    snapshots: dict = {}
    for d in store.list_dates(dataset):
        content = store.read(dataset, d).decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        symbols = [row[symbol_col] for row in reader if row.get(symbol_col)]
        snapshots[d] = symbols
    if not snapshots:
        raise ValueError(
            f"no '{dataset}' snapshots in {store.root} — run the daily "
            f"snapshot job first (scripts/snapshot_reference.py). Without "
            f"point-in-time snapshots, any backtest carries survivorship bias "
            f"(G-43)."
        )
    return PointInTimeUniverse(snapshots)
