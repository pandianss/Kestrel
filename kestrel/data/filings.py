"""Corporate-results filings — the feed for "analyse financials as filed".

Indian listed companies file quarterly/annual results to the exchanges under
SEBI LODR (~45 days after period end), as **XBRL** (structured) plus a PDF. This
module turns that feed into point-in-time `FundamentalRecord`s for the store.

Honest boundaries (the same shape as every other real source here):

  * **`parse_xbrl_facts` is solid and tested** — it extracts numeric facts from
    an XBRL instance generically (concept → {context → value}). It has no
    network and no taxonomy assumptions baked in.

  * **`extract_financials` is a heuristic that needs calibration.** Mapping
    concepts to fields and picking the *current-period* context out of an
    XBRL that also holds YTD and prior-period comparatives is genuinely
    filing-specific. The default tag map below is a reasonable starting point;
    it MUST be checked against real NSE/BSE filings before its numbers are
    trusted (like the impact-cost priors, doc 07 §4.2 — a starting value, not a
    fitted one).

  * **`NSEFilingsSource` is structured but inert without live tuning.** NSE's
    endpoints need browser-like headers/cookies and their JSON shape drifts, so
    the real fetch is left injectable and must be run + calibrated on the
    operator's host. `StaticFilings` runs the whole pipeline today.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol, runtime_checkable

from kestrel.data.fundamentals import FundamentalRecord


@dataclass(frozen=True)
class FiledResult:
    """Metadata for one results filing — enough to fetch and date it."""
    symbol: str
    period_end: date
    filing_date: date        # when it became public — the point-in-time date
    xbrl_url: str = ""


# --- XBRL parsing (generic, tested) --------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_xbrl_facts(xbrl_bytes: bytes) -> dict[str, dict[str, float]]:
    """Extract numeric facts from an XBRL instance as
    {concept_local_name: {context_ref: value}}. Non-numeric and context-less
    elements are ignored. Pure and taxonomy-agnostic."""
    root = ET.parse(io.BytesIO(xbrl_bytes)).getroot()
    facts: dict[str, dict[str, float]] = {}
    for el in root.iter():
        ctx = el.get("contextRef")
        if ctx is None or el.text is None:
            continue
        try:
            val = float(el.text.strip().replace(",", ""))
        except (ValueError, AttributeError):
            continue
        facts.setdefault(_local(el.tag), {})[ctx] = val
    return facts


#: Concept local-names for the fields we need, most-common first. A real feed
#: will surface variants; this is the starting map, to be calibrated.
DEFAULT_TAG_MAP = {
    "revenue": ["RevenueFromOperations", "Revenue", "TotalIncome"],
    "net_profit": ["ProfitLossForPeriod", "ProfitLossForThePeriod",
                   "ProfitLossAfterTaxFromContinuingOperations"],
    "basic_eps": ["BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                  "BasicEarningsPerShare", "BasicEarningsLossPerShare"],
    "equity_capital": ["PaidUpValueOfEquityShareCapital", "PaidUpEquityShareCapital"],
}


def extract_financials(
    xbrl_bytes: bytes,
    *,
    tag_map: dict[str, list[str]] = DEFAULT_TAG_MAP,
    prefer_context: str | None = None,
) -> dict[str, float | None]:
    """Pull the fields we need from an XBRL filing. ⚠️ Heuristic — see module
    docstring. For each field, the first matching concept is used; the value is
    from `prefer_context` if given, else the fact with the largest magnitude
    (a rough 'headline / current period' pick that must be validated against
    real filings)."""
    facts = parse_xbrl_facts(xbrl_bytes)
    out: dict[str, float | None] = {}
    for field, concepts in tag_map.items():
        val: float | None = None
        for c in concepts:
            if c in facts:
                by_ctx = facts[c]
                if prefer_context and prefer_context in by_ctx:
                    val = by_ctx[prefer_context]
                else:
                    val = max(by_ctx.values(), key=abs)
                break
        out[field] = val
    return out


# --- sources -------------------------------------------------------------

@runtime_checkable
class FilingsSource(Protocol):
    def recent(self, since: date) -> list[FiledResult]:
        """Results filed on/after `since`."""
        ...

    def fetch_xbrl(self, filed: FiledResult) -> bytes:
        """The raw XBRL for a filing."""
        ...


class StaticFilings:
    """Dev source: filings and their XBRL supplied in-memory, so the ingestion
    pipeline runs end-to-end today."""

    def __init__(self, filings: list[tuple[FiledResult, bytes]]):
        self._items = list(filings)

    def recent(self, since: date) -> list[FiledResult]:
        return [f for f, _ in self._items if f.filing_date >= since]

    def fetch_xbrl(self, filed: FiledResult) -> bytes:
        for f, x in self._items:
            if f == filed:
                return x
        raise KeyError(filed)


_NSE_RESULTS_URL = "https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly"


class NSEFilingsSource:
    """NSE corporate financial-results feed. Structured but **inert without live
    tuning**: NSE requires browser-like headers and a session cookie, and the
    JSON shape drifts. The HTTP getter is injectable; the real getter must be
    supplied and calibrated on the operator's host (doc 11 fundamentals feed)."""

    def __init__(self, http: Callable[[str], bytes] | None = None):
        self._http = http

    def recent(self, since: date) -> list[FiledResult]:
        if self._http is None:
            raise RuntimeError(
                "NSEFilingsSource needs a live HTTP getter with NSE session "
                "headers/cookies — not available unauthenticated. Calibrate it "
                "on-host, or use StaticFilings for development."
            )
        import json

        rows = json.loads(self._http(_NSE_RESULTS_URL))
        out: list[FiledResult] = []
        for r in rows:
            try:
                fd = date.fromisoformat(r["filingDate"][:10])
                if fd < since:
                    continue
                out.append(FiledResult(
                    symbol=r["symbol"],
                    period_end=date.fromisoformat(r["toDate"][:10]),
                    filing_date=fd,
                    xbrl_url=r.get("xbrl", ""),
                ))
            except (KeyError, ValueError):
                continue   # shape drift on a row is skipped, not fatal
        return out

    def fetch_xbrl(self, filed: FiledResult) -> bytes:
        if self._http is None or not filed.xbrl_url:
            raise RuntimeError("no live HTTP getter / XBRL url for this filing")
        return self._http(filed.xbrl_url)


def to_record(filed: FiledResult, *, eps_ttm: float, book_value_per_share: float,
              roe: float | None = None) -> FundamentalRecord:
    """Build a point-in-time FundamentalRecord from a filing, dated by its
    filing_date (the only date a backtest may trust it from)."""
    return FundamentalRecord(
        symbol=filed.symbol,
        period_end=filed.period_end,
        publish_date=filed.filing_date,
        eps_ttm=eps_ttm,
        book_value_per_share=book_value_per_share,
        roe=roe,
    )
