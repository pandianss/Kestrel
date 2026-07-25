"""Tests for XBRL parsing and the filings → fundamentals ingestion."""
import json
from datetime import date

import pytest

from kestrel.data.filings import (
    AmbiguousContextError,
    FiledResult,
    NSEFilingsSource,
    StaticFilings,
    extract_financials,
    financials_by_context,
    parse_xbrl_facts,
    to_record,
)
from kestrel.data.fundamentals_store import FundamentalsStore

# Shaped after a real NSE INDAS results XBRL (2026-07-25 calibration): the SAME
# period appears under two contexts (OneD, FourD) with DIFFERENT values — the
# ambiguity that must not be guessed.
SAMPLE_XBRL = (
    b'<xbrl xmlns:f="urn:x">'
    b'<f:RevenueFromOperations contextRef="OneD">3327000</f:RevenueFromOperations>'
    b'<f:ProfitLossForPeriod contextRef="OneD">-9237000</f:ProfitLossForPeriod>'
    b'<f:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations contextRef="OneD">-0.71</f:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations>'
    b'<f:ProfitLossForPeriod contextRef="FourD">1293000</f:ProfitLossForPeriod>'
    b'<f:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations contextRef="FourD">0.10</f:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations>'
    b'<f:NameOfTheCompany contextRef="OneD">Ignore Me Ltd</f:NameOfTheCompany>'   # non-numeric
    b'</xbrl>'
)

# A single-context filing (unambiguous)
ONE_CTX_XBRL = (
    b'<xbrl><BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations contextRef="OneD">'
    b'9.0</BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations>'
    b'<ProfitLossForPeriod contextRef="OneD">150000</ProfitLossForPeriod></xbrl>'
)


def test_parse_xbrl_facts_extracts_numeric_by_context():
    facts = parse_xbrl_facts(SAMPLE_XBRL)
    assert facts["ProfitLossForPeriod"] == {"OneD": -9_237_000.0, "FourD": 1_293_000.0}
    assert "NameOfTheCompany" not in facts          # non-numeric ignored


def test_financials_by_context_exposes_all_candidates():
    by = financials_by_context(SAMPLE_XBRL)
    assert by["OneD"]["basic_eps"] == -0.71 and by["OneD"]["net_profit"] == -9_237_000.0
    assert by["FourD"]["basic_eps"] == 0.10


def test_extract_financials_raises_on_ambiguous_context():
    # OneD vs FourD disagree -> never guess
    with pytest.raises(AmbiguousContextError):
        extract_financials(SAMPLE_XBRL)


def test_extract_financials_uses_explicit_context():
    assert extract_financials(SAMPLE_XBRL, context="OneD")["basic_eps"] == -0.71
    assert extract_financials(SAMPLE_XBRL, context="FourD")["basic_eps"] == 0.10


def test_extract_financials_single_context_is_unambiguous():
    fin = extract_financials(ONE_CTX_XBRL)
    assert fin["basic_eps"] == 9.0 and fin["net_profit"] == 150_000.0


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
    # real NSE shapes: DD-Mon-YYYY dates, filingDate carries a time, xbrl is a .xml URL
    rows = [
        {"symbol": "TCS", "toDate": "30-Jun-2024", "filingDate": "11-Jul-2024 16:39",
         "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/a.xml"},
        {"symbol": "NOXBRL", "toDate": "30-Jun-2024", "filingDate": "11-Jul-2024 16:39",
         "xbrl": "-"},   # placeholder — must be skipped
    ]
    src = NSEFilingsSource(http=lambda url: json.dumps(rows).encode())
    got = src.recent(date(2024, 1, 1))
    assert len(got) == 1 and got[0].symbol == "TCS"
    assert got[0].period_end == date(2024, 6, 30) and got[0].filing_date == date(2024, 7, 11)


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
