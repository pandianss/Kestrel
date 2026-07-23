"""Tests for the reference-data snapshotter — the D-15 / G-43 keystone.

The no-overwrite invariant is the whole reason this component exists, so it is
tested from several angles: idempotent same-content writes, hard failure on
different-content writes, integrity detection, and correct point-in-time
`asof` retrieval.
"""
from datetime import date

import pytest

from kestrel.data.pit import build_pit_universe
from kestrel.data.reference import StaticListSource
from kestrel.data.snapshot import SnapshotConflictError, SnapshotStore


def test_write_then_read_roundtrip(tmp_path):
    store = SnapshotStore(tmp_path)
    m = store.write("instruments", date(2026, 1, 5), b"a,b\n1,2\n", source="dev")
    assert store.exists("instruments", date(2026, 1, 5))
    assert store.read("instruments", date(2026, 1, 5)) == b"a,b\n1,2\n"
    assert m.size_bytes == 8 and m.source == "dev"


def test_same_content_rewrite_is_idempotent(tmp_path):
    """Re-running the daily job with identical data must be a safe no-op."""
    store = SnapshotStore(tmp_path)
    d = date(2026, 1, 5)
    m1 = store.write("instruments", d, b"same", source="dev")
    m2 = store.write("instruments", d, b"same", source="dev")   # must not raise
    assert m1.sha256 == m2.sha256


def test_different_content_same_date_raises(tmp_path):
    """The D-15 guarantee: never silently overwrite. A different dataset for a
    date that already exists is a hard error, not a replace."""
    store = SnapshotStore(tmp_path)
    d = date(2026, 1, 5)
    store.write("instruments", d, b"original", source="dev")
    with pytest.raises(SnapshotConflictError):
        store.write("instruments", d, b"DIFFERENT", source="dev")
    # original survives untouched
    assert store.read("instruments", d) == b"original"


def test_integrity_failure_detected(tmp_path):
    """A tampered/corrupted snapshot must be caught on read, not served."""
    store = SnapshotStore(tmp_path)
    d = date(2026, 1, 5)
    store.write("instruments", d, b"payload", source="dev")
    # corrupt the data file behind the manifest
    data_file = store._data_path("instruments", d, "csv")
    import os
    os.chmod(data_file, 0o600)
    data_file.write_bytes(b"tampered")
    with pytest.raises(IOError):
        store.read("instruments", d)


def test_asof_returns_latest_on_or_before(tmp_path):
    store = SnapshotStore(tmp_path)
    store.write("instruments", date(2026, 1, 1), b"jan", source="dev")
    store.write("instruments", date(2026, 3, 1), b"mar", source="dev")
    assert store.asof("instruments", date(2026, 2, 15)) == b"jan"   # not the future
    assert store.asof("instruments", date(2026, 3, 1)) == b"mar"
    assert store.asof("instruments", date(2025, 12, 1)) is None     # before first


def test_snapshot_to_pit_universe_loop(tmp_path):
    """End-to-end: dev source -> snapshot -> point-in-time universe. The
    universe must be flagged NOT survivorship-biased, and reflect membership
    changes across snapshot dates."""
    store = SnapshotStore(tmp_path)
    store.write("instruments", date(2026, 1, 1),
                StaticListSource(["A", "B"]).fetch(), source="dev")
    store.write("instruments", date(2026, 6, 1),
                StaticListSource(["A", "B", "C"]).fetch(), source="dev")
    uni = build_pit_universe(store)
    assert uni.is_survivorship_biased is False
    assert set(uni.members_asof(date(2026, 3, 1))) == {"A", "B"}
    assert set(uni.members_asof(date(2026, 7, 1))) == {"A", "B", "C"}


def test_empty_store_pit_raises(tmp_path):
    with pytest.raises(ValueError):
        build_pit_universe(SnapshotStore(tmp_path))
