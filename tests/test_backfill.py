"""Tests for the fundamentals history backfill (basis preference, resumable)."""
from datetime import date

from kestrel.data.filings import FiledResult, StaticFilings, report_basis
from kestrel.data.fundamentals_store import FundamentalsStore
from scripts.backfill_fundamentals import backfill_symbol

_EPS = "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations"
_NAT = "NatureOfReportStandaloneConsolidated"


def _xbrl(eps: float, nature: str) -> bytes:
    return (f'<xbrl><{_NAT} contextRef="OneD">{nature}</{_NAT}>'
            f'<{_EPS} contextRef="OneD">{eps}</{_EPS}></xbrl>').encode()


def test_report_basis_reads_nature():
    assert report_basis(_xbrl(5, "Consolidated")) == "consolidated"
    assert report_basis(_xbrl(5, "Standalone")) == "standalone"
    assert report_basis(b"<xbrl/>") == "unknown"


def _source():
    q1 = date(2024, 3, 31)
    q2 = date(2024, 6, 30)
    return StaticFilings([
        (FiledResult("X", q1, date(2024, 5, 15), "std1.xml"), _xbrl(5.0, "Standalone")),
        (FiledResult("X", q1, date(2024, 5, 15), "con1.xml"), _xbrl(6.0, "Consolidated")),
        (FiledResult("X", q2, date(2024, 8, 14), "con2.xml"), _xbrl(7.0, "Consolidated")),
    ])


def test_backfill_prefers_consolidated_one_per_quarter(tmp_path):
    store = FundamentalsStore(tmp_path)
    r = backfill_symbol(_source(), store, "X", pause=0, sleep=lambda s: None, log=lambda m: None)
    assert r["written"] == 2                       # two quarters, not three filings
    recs = {rec.period_end: rec.eps_ttm for rec in store.records("X")}
    assert recs[date(2024, 3, 31)] == 6.0          # consolidated chosen over standalone 5.0
    assert recs[date(2024, 6, 30)] == 7.0


def test_backfill_is_resumable(tmp_path):
    store = FundamentalsStore(tmp_path)
    backfill_symbol(_source(), store, "X", pause=0, sleep=lambda s: None, log=lambda m: None)
    r2 = backfill_symbol(_source(), store, "X", pause=0, sleep=lambda s: None, log=lambda m: None)
    assert r2["written"] == 0 and r2["fetched"] == 0   # both quarters known -> no re-fetch
