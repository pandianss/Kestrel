"""Tests for the VERIFIABLE relations extractor (no fabricated data).

The extractor must emit only what a filing / NSE classification asserts, with
the source recorded — segment revenue shares from the XBRL's own SegmentRevenue,
industry from NSE constituents, and NO invented corporate relations."""
from datetime import date

from kestrel.data.filings import FiledResult, StaticFilings
from kestrel.data.relations import RelationType
from kestrel.data.relations_extractor import (
    extract_promoter_relations,
    extract_segments,
    extract_symbol_relations,
    harvest_all_relations,
)
from kestrel.data.relations_store import RelationsStore

# XBRL with two segments across two periods (quarter + YTD contexts), consolidated.
_XBRL = (
    '<xbrl>'
    '<NatureOfReportStandaloneConsolidated contextRef="C0">Consolidated</NatureOfReportStandaloneConsolidated>'
    '<DescriptionOfReportableSegment contextRef="Aq">Alpha</DescriptionOfReportableSegment>'
    '<SegmentRevenue contextRef="Aq">300</SegmentRevenue>'
    '<DescriptionOfReportableSegment contextRef="Ay">Alpha</DescriptionOfReportableSegment>'
    '<SegmentRevenue contextRef="Ay">900</SegmentRevenue>'
    '<DescriptionOfReportableSegment contextRef="Bq">Beta</DescriptionOfReportableSegment>'
    '<SegmentRevenue contextRef="Bq">100</SegmentRevenue>'
    '<DescriptionOfReportableSegment contextRef="By">Beta</DescriptionOfReportableSegment>'
    '<SegmentRevenue contextRef="By">300</SegmentRevenue>'
    '</xbrl>'
).encode()


def test_extract_segments_from_filing_revenue():
    segs = dict(extract_segments(_XBRL))
    # per-segment largest positive (YTD): Alpha 900, Beta 300 -> 75% / 25%
    assert round(segs["Alpha"], 3) == 0.75
    assert round(segs["Beta"], 3) == 0.25


def test_extract_segments_empty_when_no_segment_revenue():
    assert extract_segments(b"<xbrl><Foo contextRef='C'>1</Foo></xbrl>") == []


def _source():
    return StaticFilings([
        (FiledResult("X", date(2024, 3, 31), date(2024, 5, 15), "std.xml"),
         _XBRL.replace(b"Consolidated", b"Standalone")),
        (FiledResult("X", date(2024, 3, 31), date(2024, 5, 15), "con.xml"), _XBRL),
    ])


def test_extract_symbol_writes_verifiable_segments_and_industry(tmp_path):
    store = RelationsStore(tmp_path)
    src = _source()
    c = extract_symbol_relations("X", src.recent(date(2000, 1, 1)), src.fetch_xbrl,
                                 store, industry="Energy")
    assert c["segments"] == 2 and c["industry"] == 1
    assert c["relations"] == 0          # never fabricated

    segs = store.segments_asof("X", date(2025, 1, 1))
    assert {s.segment_name for s in segs} == {"Alpha", "Beta"}
    assert all(s.source == "con.xml" for s in segs)      # provenance = consolidated filing
    ind = store.industry_asof("X", date(2025, 1, 1))
    assert ind.primary_industry == "Energy" and ind.sub_sector == ""   # blank, not guessed
    assert ind.source == "nse:indices/constituents"


_SHP = [
    {"pr_and_prgrp": 50.48, "broadcastDate": "16-JUL-2026 19:24:44", "date": "30-JUN-2026"},
    {"pr_and_prgrp": 50.30, "broadcastDate": "18-APR-2026 10:00:00", "date": "31-MAR-2026"},
    {"pr_and_prgrp": None, "broadcastDate": "x", "date": "y"},   # skipped
]


def test_extract_promoter_relations_from_shareholding():
    rels = extract_promoter_relations("X", _SHP, source="u")
    assert len(rels) == 2
    r = rels[0]
    assert r.relation_type is RelationType.PROMOTER_GROUP
    assert r.target_name_or_symbol == "Promoter & Promoter Group"
    assert r.holding_pct == 0.5048 and r.publish_date == date(2026, 7, 16)  # UPPER date parsed
    assert r.source == "u"


def test_extract_symbol_writes_promoter_relations(tmp_path):
    store = RelationsStore(tmp_path)
    src = _source()
    c = extract_symbol_relations("X", src.recent(date(2000, 1, 1)), src.fetch_xbrl, store,
                                 industry="Energy", shareholding_rows=_SHP)
    assert c["relations"] == 2          # both quarters stored to history
    rels = store.relations_asof("X", date(2027, 1, 1))
    assert len(rels) == 1               # asof returns the latest per target
    assert rels[0].holding_pct == 0.5048
    assert rels[0].source.startswith("https://www.nseindia.com/api/")
    # the older disclosure is the point-in-time view before the newer one
    assert store.relations_asof("X", date(2026, 5, 1))[0].holding_pct == 0.503


def test_no_industry_written_when_unknown(tmp_path):
    store = RelationsStore(tmp_path)
    src = _source()
    c = extract_symbol_relations("X", src.recent(date(2000, 1, 1)), src.fetch_xbrl,
                                 store, industry=None)   # no NSE classification
    assert c["industry"] == 0           # left blank, not invented


def test_harvest_is_resumable(tmp_path):
    store_root = tmp_path / "rel"
    src, ind = _source(), {"X": "Energy"}
    a = harvest_all_relations("unused", store_root, source=src, industry=ind,
                              symbols=["X"], refresh_days=0)
    assert a["segments_added"] == 2 and a["industry_added"] == 1
    # refresh_days large -> X is fresh -> skipped, nothing re-fetched
    b = harvest_all_relations("unused", store_root, source=src, industry=ind,
                              symbols=["X"], refresh_days=9999)
    assert b["symbols_processed"] == 0
