"""Tests for XBRL parsing and the filings → fundamentals ingestion."""
import json
from datetime import date

import pytest

from kestrel.data.filings import (
    FiledResult,
    NSEFilingsSource,
    StaticFilings,
    extract_financials,
    parse_xbrl_facts,
    to_record,
)
from kestrel.data.fundamentals_store import FundamentalsStore

SAMPLE_XBRL = (
    b'<xbrl xmlns:f="urn:x">'
    b'<f:RevenueFromOperations contextRef="Q3" unitRef="INR">1000000</f:RevenueFromOperations>'
    b'<f:RevenueFromOperations contextRef="YTD" unitRef="INR">2500000</f:RevenueFromOperations>'
    b'<f:ProfitLossForPeriod contextRef="Q3" unitRef="INR">150000</f:ProfitLossForPeriod>'
    b'<f:BasicEarningsPerShare contextRef="Q3" unitRef="INR">12.5</f:BasicEarningsPerShare>'
    b'<f:CompanyName contextRef="Q3">Ignore Me Ltd</f:CompanyName>'   # non-numeric, skipped
    b'</xbrl>'
)


def test_parse_xbrl_facts_extracts_numeric_by_context():
    facts = parse_xbrl_facts(SAMPLE_XBRL)
    assert facts["RevenueFromOperations"] == {"Q3": 1_000_000.0, "YTD": 2_500_000.0}
    assert facts["ProfitLossForPeriod"]["Q3"] == 150_000.0
    assert facts["BasicEarningsPerShare"]["Q3"] == 12.5
    assert "CompanyName" not in facts          # non-numeric ignored


def test_extract_financials_maps_fields():
    fin = extract_financials(SAMPLE_XBRL)
    assert fin["basic_eps"] == 12.5
    assert fin["net_profit"] == 150_000.0
    # revenue picks the largest-magnitude context (heuristic) -> YTD here
    assert fin["revenue"] == 2_500_000.0


def test_extract_financials_prefers_context_when_given():
    fin = extract_financials(SAMPLE_XBRL, prefer_context="Q3")
    assert fin["revenue"] == 1_000_000.0


def test_extract_financials_missing_field_is_none():
    fin = extract_financials(b'<xbrl><Foo contextRef="C">1</Foo></xbrl>')
    assert fin["basic_eps"] is None


def test_static_filings_recent_and_fetch():
    f = FiledResult("X", date(2024, 3, 31), date(2024, 5, 15))
    src = StaticFilings([(f, b"<xbrl/>")])
    assert src.recent(date(2024, 1, 1)) == [f]
    assert src.recent(date(2024, 6, 1)) == []       # filed before `since`
    assert src.fetch_xbrl(f) == b"<xbrl/>"


def test_nse_source_inert_without_http():
    with pytest.raises(RuntimeError):
        NSEFilingsSource().recent(date(2024, 1, 1))


def test_nse_source_parses_injected_json():
    rows = [{"symbol": "TCS", "toDate": "2024-06-30", "filingDate": "2024-07-11", "xbrl": "u"}]
    src = NSEFilingsSource(http=lambda url: json.dumps(rows).encode())
    got = src.recent(date(2024, 1, 1))
    assert len(got) == 1 and got[0].symbol == "TCS" and got[0].period_end == date(2024, 6, 30)


def test_ingestion_writes_point_in_time_record(tmp_path):
    from scripts.ingest_fundamentals import ingest

    f = FiledResult("X", date(2024, 3, 31), date(2024, 5, 15))
    xbrl = b'<xbrl><BasicEarningsPerShare contextRef="Q">9.0</BasicEarningsPerShare></xbrl>'
    store = FundamentalsStore(tmp_path)
    n = ingest(StaticFilings([(f, xbrl)]), store, date(2000, 1, 1))
    assert n == 1
    rec = store.asof("X", date(2024, 12, 1))
    assert rec is not None and rec.eps_ttm == 9.0
    assert rec.publish_date == date(2024, 5, 15)      # dated by filing, not period end
    # before the filing was public: nothing
    assert store.asof("X", date(2024, 4, 1)) is None


def test_to_record_dates_by_filing():
    f = FiledResult("X", date(2024, 3, 31), date(2024, 5, 15))
    r = to_record(f, eps_ttm=5.0, book_value_per_share=50.0)
    assert r.publish_date == date(2024, 5, 15) and r.period_end == date(2024, 3, 31)
