"""Tests for the raw-filing archive (keep originals; reprocess without re-fetch)."""
from datetime import date

from kestrel.data.filing_archive import FilingArchive, get_xbrl
from kestrel.data.filings import FiledResult

_URL = "https://nsearchives.nseindia.com/corporate/xbrl/INDAS_1_2.xml"


def test_archive_roundtrip_and_immutable(tmp_path):
    a = FilingArchive(tmp_path)
    assert a.has("X", _URL) is False
    a.write("X", _URL, b"<xbrl>orig</xbrl>")
    assert a.has("X", _URL) and a.read("X", _URL) == b"<xbrl>orig</xbrl>"
    # write-once: a second write does not overwrite the as-filed bytes (D-15)
    a.write("X", _URL, b"DIFFERENT")
    assert a.read("X", _URL) == b"<xbrl>orig</xbrl>"


class _Src:
    def __init__(self):
        self.calls = 0

    def fetch_xbrl(self, filed):
        self.calls += 1
        return b"<fetched/>"


def test_get_xbrl_fetches_then_reads_from_archive(tmp_path):
    a = FilingArchive(tmp_path)
    src = _Src()
    filed = FiledResult("X", date(2024, 3, 31), date(2024, 5, 15), _URL)

    xb, from_archive = get_xbrl(a, src, "X", filed)
    assert xb == b"<fetched/>" and from_archive is False and src.calls == 1   # fetched + archived
    # a second call reads the archived copy — NO second network fetch
    xb2, from_archive2 = get_xbrl(a, src, "X", filed)
    assert xb2 == b"<fetched/>" and from_archive2 is True and src.calls == 1
