"""Tests for the index-constituents source and the clean stock universe."""
from datetime import date

import pytest

from kestrel.data.constituents import NSEConstituentsSource, parse_symbols
from kestrel.data.pit import build_index_universe
from kestrel.data.snapshot import SnapshotStore

CSV = (
    b"Company Name,Industry,Symbol,Series,ISIN Code\n"
    b"Reliance Industries Ltd.,Energy,RELIANCE,EQ,INE002A01018\n"
    b"Tata Consultancy Services Ltd.,IT,TCS,EQ,INE467B01029\n"
    b"Some SME Ltd.,X,SMEBE,BE,INE000000001\n"
    b"Some Debt Ltd.,X,DEBT01,N1,INE000000002\n"   # non-equity series -> excluded
)


def test_parse_symbols_filters_to_equity_series():
    syms = parse_symbols(CSV)
    assert syms == ["RELIANCE", "TCS", "SMEBE"]   # DEBT01 (series N1) dropped


def test_parse_symbols_can_keep_all_series():
    assert "DEBT01" in parse_symbols(CSV, series=None)


def test_source_fetch_uses_injected_http():
    src = NSEConstituentsSource("nifty50", http=lambda url: CSV)
    assert src.dataset == "constituents_nifty50"
    assert src.source_id == "nse:indices/nifty50"
    assert src.fetch() == CSV


def test_source_rejects_unexpected_payload():
    src = NSEConstituentsSource("nifty50", http=lambda url: b"<html>blocked</html>")
    with pytest.raises(RuntimeError):
        src.fetch()


def test_unknown_index_raises():
    with pytest.raises(ValueError):
        NSEConstituentsSource("nifty999")


def test_build_index_universe_is_clean_and_pit(tmp_path):
    store = SnapshotStore(tmp_path)
    store.write("constituents_nifty500", date(2026, 7, 24), CSV, source="nse:indices/nifty500")
    uni = build_index_universe(store, "nifty500")
    assert uni.is_survivorship_biased is False
    # equity series only; debt excluded
    assert set(uni.members_asof(date(2026, 7, 24))) == {"RELIANCE", "TCS", "SMEBE"}


def test_index_universe_reflects_membership_change(tmp_path):
    store = SnapshotStore(tmp_path)
    small = b"Company Name,Industry,Symbol,Series,ISIN Code\nA Ltd,X,AAA,EQ,I1\n"
    bigger = b"Company Name,Industry,Symbol,Series,ISIN Code\nA Ltd,X,AAA,EQ,I1\nB Ltd,X,BBB,EQ,I2\n"
    store.write("constituents_nifty50", date(2026, 1, 1), small, source="nse:indices/nifty50")
    store.write("constituents_nifty50", date(2026, 6, 1), bigger, source="nse:indices/nifty50")
    uni = build_index_universe(store, "nifty50")
    assert set(uni.members_asof(date(2026, 3, 1))) == {"AAA"}         # before BBB joined
    assert set(uni.members_asof(date(2026, 7, 1))) == {"AAA", "BBB"}  # after
