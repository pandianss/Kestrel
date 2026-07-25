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
    endpoints need browser-like headers/cookies, so the real fetch is left
    injectable. `StaticFilings` runs the whole pipeline today.

Calibration against the live feed (2026-07-25) — what was learned by running it:
  * **JSON shape confirmed.** The results API returns ~3,800 rows; dates are
    'DD-Mon-YYYY' (filingDate carries a time), and many recent rows have a
    placeholder `xbrl` of '-' until the archive is populated. `recent()` now
    parses this and skips non-'.xml' rows. Verified: 3,796/3,814 parsed.
  * **Concept tags confirmed** (RevenueFromOperations, ProfitLossForPeriod,
    PaidUpValueOfEquityShareCapital, BasicEarningsLossPerShareFromContinuing…).
  * **⚠️ Context selection is unresolved and must not be guessed.** A real
    filing (ICDSLTD, Q3 FY25) carries the same period under two contexts —
    `OneD` (EPS −0.71, PAT −92.4L) and `FourD` (EPS +0.10, PAT +12.9L) — both
    tagged 'Standalone', with no distinguishing dimension. Which is the true
    current-quarter standalone figure needs the taxonomy's presentation
    linkbase or a cross-check against the company's reported number. Until that
    rule exists, `extract_financials` raises `AmbiguousContextError` rather than
    feed a coin-flip into the factors, and the ingestion skips such filings.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Protocol, runtime_checkable

from kestrel.data.fundamentals import FundamentalRecord


def _nse_date(s: str) -> date:
    """Parse NSE's 'DD-Mon-YYYY' dates (optionally with a ' HH:MM' time)."""
    return datetime.strptime(s.strip().split(" ")[0], "%d-%b-%Y").date()


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


#: Concept local-names for the fields we need — CONFIRMED against a real NSE
#: INDAS results XBRL (2026-07-25 calibration). Most-common first; a real feed
#: still surfaces variants.
DEFAULT_TAG_MAP = {
    "revenue": ["RevenueFromOperations", "Revenue", "TotalIncome"],
    "net_profit": ["ProfitLossForPeriod", "ProfitLossForPeriodFromContinuingOperations"],
    "basic_eps": ["BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                  "BasicEarningsLossPerShareFromContinuingOperations",
                  "BasicEarningsPerShare"],
    "equity_capital": ["PaidUpValueOfEquityShareCapital", "PaidUpEquityShareCapital"],
    "face_value": ["FaceValueOfEquityShareCapital"],
}


class AmbiguousContextError(Exception):
    """Raised when a filing has several period contexts and none was specified.
    Discovered during 2026-07-25 calibration: an NSE INDAS results XBRL can hold
    multiple contexts with the SAME period and nature yet DIFFERENT values
    (e.g. OneD vs FourD). Picking one by a heuristic silently risks the wrong
    number — the caller must choose the context explicitly (validated per the
    presentation linkbase or cross-checked against the company's reported
    figure) rather than let the parser guess."""


def financials_by_context(
    xbrl_bytes: bytes, *, tag_map: dict[str, list[str]] = DEFAULT_TAG_MAP
) -> dict[str, dict[str, float | None]]:
    """{context_ref: {field: value}} for every context that carries any mapped
    field. This is the honest primitive: it exposes *all* candidates rather than
    collapsing to one, so the ambiguity is visible instead of hidden."""
    facts = parse_xbrl_facts(xbrl_bytes)
    contexts: set[str] = set()
    for concepts in tag_map.values():
        for c in concepts:
            contexts.update(facts.get(c, {}).keys())
    out: dict[str, dict[str, float | None]] = {}
    for ctx in sorted(contexts):
        fields: dict[str, float | None] = {}
        for field, concepts in tag_map.items():
            val: float | None = None
            for c in concepts:
                if c in facts and ctx in facts[c]:
                    val = facts[c][ctx]
                    break
            fields[field] = val
        out[ctx] = fields
    return out


def extract_financials(
    xbrl_bytes: bytes,
    *,
    tag_map: dict[str, list[str]] = DEFAULT_TAG_MAP,
    context: str | None = None,
) -> dict[str, float | None]:
    """The mapped fields for one context. If `context` is given, that context is
    used. If the filing has exactly one period context, it is used. Otherwise
    `AmbiguousContextError` — never a silent guess (2026-07-25 calibration)."""
    by = financials_by_context(xbrl_bytes, tag_map=tag_map)
    if context is not None:
        if context not in by:
            raise KeyError(f"context {context!r} not in filing; have {sorted(by)}")
        return by[context]
    if len(by) == 1:
        return next(iter(by.values()))
    raise AmbiguousContextError(
        f"{len(by)} period contexts {sorted(by)} carry different values — pass "
        f"context=... explicitly (see filings.py calibration note)."
    )


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
        if isinstance(rows, dict):
            rows = rows.get("data", [])
        out: list[FiledResult] = []
        for r in rows:
            try:
                xbrl = r.get("xbrl", "")
                if not xbrl.lower().endswith(".xml"):
                    continue   # rows without a real XBRL (placeholder "-") are useless
                fd = _nse_date(r["filingDate"])   # "25-Jun-2026 16:39" -> date
                if fd < since:
                    continue
                out.append(FiledResult(
                    symbol=r["symbol"],
                    period_end=_nse_date(r["toDate"]),   # "31-Dec-2024"
                    filing_date=fd,
                    xbrl_url=xbrl,
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
