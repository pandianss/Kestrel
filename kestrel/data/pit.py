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
    source_prefix: str | None = "kite:",
) -> PointInTimeUniverse:
    """Read every instruments snapshot in `store` into dated membership and
    return a PointInTimeUniverse. Each snapshot date contributes the set of
    symbols tradeable as of that date.

    `source_prefix` filters by provenance (the manifest `source`): by default
    only real Kite snapshots (`kite:*`) are admitted, so a dev-stub snapshot
    left in the store can never contaminate the universe — a dev day would
    otherwise claim only a handful of symbols were tradeable. Pass `None` to
    accept every source (tests, or an all-dev store). This is non-destructive
    (D-15): the dev snapshot stays on disk; it is simply not trusted as a
    real trading-day universe.
    """
    snapshots: dict = {}
    skipped: list = []
    for d in store.list_dates(dataset):
        if source_prefix is not None:
            manifest = store.read_manifest(dataset, d)
            if manifest is not None and not manifest.source.startswith(source_prefix):
                skipped.append((d, manifest.source))
                continue
        content = store.read(dataset, d).decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        symbols = [row[symbol_col] for row in reader if row.get(symbol_col)]
        snapshots[d] = symbols
    if not snapshots:
        note = ""
        if skipped:
            note = (
                f" ({len(skipped)} snapshot(s) skipped for not matching "
                f"source_prefix={source_prefix!r}: e.g. {skipped[0][1]})"
            )
        raise ValueError(
            f"no admissible '{dataset}' snapshots in {store.root}{note} — run the "
            f"daily snapshot job (scripts/snapshot_reference.py --require-live). "
            f"Without point-in-time snapshots, any backtest carries survivorship "
            f"bias (G-43)."
        )
    return PointInTimeUniverse(snapshots)
