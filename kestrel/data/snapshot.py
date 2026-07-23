"""Immutable, dated reference-data snapshots — the G-43 / D-15 keystone.

The design's single most time-sensitive gap: reference data (the instruments
master, F&O ban list, circuit limits) is regenerated daily by the exchange and
**overwritten** by a naive loader. Once overwritten, the as-of view is gone —
and the 2026-07-23 backtest proved that costs ~18 points of fake CAGR from
survivorship alone (doc 11, G-43). The data is free to capture today and
impossible to reconstruct later.

`SnapshotStore` is the fix, and it enforces two invariants that are the whole
point:

  * **No destruction of data (D-15).** A snapshot for a given (dataset, date)
    is written once. A second write with *different* content raises — it never
    silently overwrites. A second write with *identical* content is an
    idempotent no-op, so re-running the daily job is safe.

  * **Point-in-time retrieval.** `asof(dataset, d)` returns the snapshot as it
    stood on the latest date <= d — exactly what a backtest needs to avoid
    look-ahead in its universe (feeds `PointInTimeUniverse`).

Each snapshot carries a manifest (sha256, source, retrieved_at, byte size) so
integrity is verifiable and provenance is recorded.

Layout on disk:

    <root>/<dataset>/<YYYY-MM-DD>/data.<ext>
    <root>/<dataset>/<YYYY-MM-DD>/manifest.json
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path


class SnapshotConflictError(Exception):
    """Raised when a second, *different* write is attempted for a
    (dataset, date) that already exists. This is D-15 refusing to destroy
    data — never caught-and-overwritten; investigate the source instead."""


@dataclass(frozen=True)
class Manifest:
    dataset: str
    snapshot_date: str      # ISO date the data represents (as-of)
    retrieved_at: str       # ISO datetime the fetch happened (UTC)
    source: str
    sha256: str
    size_bytes: int
    ext: str


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _make_readonly(path: Path) -> None:
    """Best-effort immutability: drop write bits. Advisory, not a security
    control — the real guarantee is the no-overwrite check, which does not
    trust the filesystem."""
    try:
        os.chmod(path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    except OSError:
        pass


class SnapshotStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    # ---- paths ---------------------------------------------------------
    def _dir(self, dataset: str, d: date) -> Path:
        return self.root / dataset / d.isoformat()

    def _data_path(self, dataset: str, d: date, ext: str) -> Path:
        return self._dir(dataset, d) / f"data.{ext}"

    def _manifest_path(self, dataset: str, d: date) -> Path:
        return self._dir(dataset, d) / "manifest.json"

    # ---- write ---------------------------------------------------------
    def write(
        self,
        dataset: str,
        snapshot_date: date,
        content: bytes,
        *,
        source: str,
        ext: str = "csv",
    ) -> Manifest:
        """Persist one snapshot. Idempotent for identical content; raises
        `SnapshotConflictError` if a *different* snapshot already exists for
        this (dataset, date) — the D-15 no-destruction guarantee."""
        existing = self.read_manifest(dataset, snapshot_date)
        digest = _sha256(content)
        if existing is not None:
            if existing.sha256 == digest:
                return existing  # idempotent: same day, same data, re-run safe
            raise SnapshotConflictError(
                f"{dataset} {snapshot_date}: a different snapshot already exists "
                f"(stored {existing.sha256[:12]}, new {digest[:12]}). "
                f"D-15 forbids overwriting — investigate the source, do not force."
            )

        d = self._dir(dataset, snapshot_date)
        d.mkdir(parents=True, exist_ok=True)
        data_path = self._data_path(dataset, snapshot_date, ext)
        data_path.write_bytes(content)
        _make_readonly(data_path)

        manifest = Manifest(
            dataset=dataset,
            snapshot_date=snapshot_date.isoformat(),
            retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            source=source,
            sha256=digest,
            size_bytes=len(content),
            ext=ext,
        )
        mp = self._manifest_path(dataset, snapshot_date)
        mp.write_text(json.dumps(asdict(manifest), indent=2))
        _make_readonly(mp)
        return manifest

    # ---- read ----------------------------------------------------------
    def exists(self, dataset: str, d: date) -> bool:
        return self._manifest_path(dataset, d).exists()

    def read_manifest(self, dataset: str, d: date) -> Manifest | None:
        mp = self._manifest_path(dataset, d)
        if not mp.exists():
            return None
        return Manifest(**json.loads(mp.read_text()))

    def read(self, dataset: str, d: date) -> bytes:
        m = self.read_manifest(dataset, d)
        if m is None:
            raise FileNotFoundError(f"no snapshot for {dataset} {d}")
        content = self._data_path(dataset, d, m.ext).read_bytes()
        if _sha256(content) != m.sha256:
            raise IOError(
                f"integrity failure: {dataset} {d} content does not match manifest "
                f"sha256 — the snapshot has been tampered with or corrupted."
            )
        return content

    def list_dates(self, dataset: str) -> list[date]:
        base = self.root / dataset
        if not base.exists():
            return []
        out = []
        for child in base.iterdir():
            if child.is_dir():
                try:
                    out.append(date.fromisoformat(child.name))
                except ValueError:
                    continue
        return sorted(out)

    def asof(self, dataset: str, d: date) -> bytes | None:
        """The snapshot as it stood on the latest date <= d. This is the
        point-in-time query a backtest needs — never a future snapshot."""
        candidates = [s for s in self.list_dates(dataset) if s <= d]
        if not candidates:
            return None
        return self.read(dataset, candidates[-1])
