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
  * **✅ Context selection RESOLVED empirically (2026-07-25).** The INDAS
    quarterly context IDs are the *columns* of the results statement, and
    **`OneD` is the current reporting quarter** (`FourD` is the year-to-date).
    Confirmed by cross-checking known quarterly EPS across ITC/RELIANCE/INFY/
    TCS Q3 FY25: `OneD` matched the ~quarterly figure (TCS 34.21, INFY 15.31,
    RELIANCE 6.44, ITC 3.95) while `FourD` was ~3x — the 9-month YTD (TCS
    100.40, ...). The XBRL <period> tags are unreliable (both read as the
    quarter); the column convention is the truth. `current_quarter_financials`
    applies this; `extract_financials` still refuses to *guess* when asked with
    no context, so the guard remains for any non-conforming filing.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Protocol, runtime_checkable

from kestrel.data.fundamentals import FundamentalRecord


def _nse_date(s: str) -> date:
    """Parse NSE's 'DD-Mon-YYYY' dates (optionally with a ' HH:MM' time). Raises
    ValueError on a null/empty value (some integrated-filing rows carry a null
    date) so a single bad row is skipped, not the whole symbol's feed."""
    if not s or not s.strip():
        raise ValueError("empty date")
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


def report_basis(xbrl_bytes: bytes) -> str:
    """'consolidated' / 'standalone' / 'unknown' from a results XBRL. A company
    files both; a trend series must stick to one basis (consolidated is the
    headline). Read from the NatureOfReportStandaloneConsolidated text fact."""
    root = ET.parse(io.BytesIO(xbrl_bytes)).getroot()
    for el in root.iter():
        if _local(el.tag) == "NatureOfReportStandaloneConsolidated" and el.text:
            t = el.text.strip().lower()
            if "consolidat" in t:
                return "consolidated"
            if "standalone" in t:
                return "standalone"
    return "unknown"


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
    "other_equity": ["OtherEquity", "ReservesAndSurplus"],
    "equity": ["Equity", "TotalEquity", "EquityAttributableToOwnersOfParent"],
    # verified against a real INDAS balance sheet (2026-07-26): the tags are
    # Borrowings{Noncurrent,Current}, not the reversed word order.
    "noncurrent_borrowings": ["BorrowingsNoncurrent", "NoncurrentBorrowings", "LongTermBorrowings"],
    "current_borrowings": ["BorrowingsCurrent", "CurrentBorrowings", "ShortTermBorrowings"],
    "borrowings": ["Borrowings"],
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


#: Empirically resolved (2026-07-25): in the NSE INDAS quarterly taxonomy the
#: context ids are the columns of the results statement; "OneD" is the current
#: reporting quarter (see module docstring for the ITC/RELIANCE/INFY/TCS check).
CURRENT_QUARTER_CONTEXT = "OneD"


def current_quarter_financials(
    xbrl_bytes: bytes, *, tag_map: dict[str, list[str]] = DEFAULT_TAG_MAP
) -> dict[str, float | None]:
    """The current-quarter fields — the resolved default for factor ingestion.
    Uses the `OneD` column; falls back to the sole context if a filing has only
    one; raises `AmbiguousContextError` for a multi-context filing that lacks
    `OneD` (non-conforming — do not guess)."""
    by = financials_by_context(xbrl_bytes, tag_map=tag_map)
    if CURRENT_QUARTER_CONTEXT in by:
        return by[CURRENT_QUARTER_CONTEXT]
    if len(by) == 1:
        return next(iter(by.values()))
    raise AmbiguousContextError(
        f"no '{CURRENT_QUARTER_CONTEXT}' context and {len(by)} candidates "
        f"{sorted(by)} — non-conforming filing, resolve explicitly."
    )


#: Balance-sheet facts are reported at an INSTANT context (period-end), not the
#: OneD duration context that carries the P&L. NSE's convention for the current
#: period-end instant is "OneI".
BALANCE_SHEET_CONTEXT = "OneI"


def current_period_financials(
    xbrl_bytes: bytes, *, tag_map: dict[str, list[str]] = DEFAULT_TAG_MAP
) -> dict[str, float | None]:
    """P&L (current quarter, OneD) merged with the balance sheet (period-end
    instant, OneI). This is what `build_record_from_financials` needs — revenue/
    profit/EPS come from OneD, equity/borrowings from OneI. Balance-sheet fields
    are simply absent (None) in a pure-quarterly filing that carries no BS."""
    by = financials_by_context(xbrl_bytes, tag_map=tag_map)
    pl = dict(current_quarter_financials(xbrl_bytes, tag_map=tag_map))   # OneD (or lone/raise)
    for field, val in (by.get(BALANCE_SHEET_CONTEXT) or {}).items():
        if pl.get(field) is None and val is not None:
            pl[field] = val
    return pl


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

    def recent(self, since: date, *, symbol: str | None = None) -> list[FiledResult]:
        return [f for f, _ in self._items
                if f.filing_date >= since and (symbol is None or f.symbol == symbol)]

    def fetch_xbrl(self, filed: FiledResult) -> bytes:
        for f, x in self._items:
            if f == filed:
                return x
        raise KeyError(filed)


_NSE_RESULTS_URL = "https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly"
#: NSE's "Integrated Filing" results feed. The legacy feed above went stale — it
#: stopped serving new quarters at Dec-2024 (~early 2025, when NSE migrated
#: results to Integrated Filing). This feed carries the current quarters but only
#: reaches back to 2025, so the two are merged for full history + current data.
_NSE_INTEGRATED_URL = ("https://www.nseindia.com/api/integrated-filing-results"
                       "?index=equities&period=Quarterly&type=Integrated%20Filing-%20Financials")


class NSEFilingsSource:
    """NSE corporate financial-results feed. Structured but **inert without live
    tuning**: NSE requires browser-like headers and a session cookie, and the
    JSON shape drifts. The HTTP getter is injectable; the real getter must be
    supplied and calibrated on the operator's host (doc 11 fundamentals feed)."""

    def __init__(self, http: Callable[[str], bytes] | None = None):
        self._http = http

    def recent(self, since: date, *, symbol: str | None = None) -> list[FiledResult]:
        """Results filed on/after `since`. With `symbol`, that one company's
        history; otherwise the current season across companies.

        Merges TWO NSE feeds because neither is complete on its own: the legacy
        `corporates-financial-results` feed holds full history but is FROZEN at
        the Dec-2024 quarter, while `integrated-filing-results` is current but
        only reaches back to 2025. De-duped by XBRL URL (they barely overlap at
        the 2024/2025 boundary). A failure of one feed must not sink the other."""
        if self._http is None:
            raise RuntimeError(
                "NSEFilingsSource needs a live HTTP getter with NSE session "
                "headers/cookies — not available unauthenticated. Calibrate it "
                "on-host, or use StaticFilings for development."
            )
        out: list[FiledResult] = []
        seen: set[str] = set()
        for fetch in (self._fetch_legacy, self._fetch_integrated):
            try:
                rows = fetch(since, symbol)
            except Exception:  # noqa: BLE001 — a dead/changed feed shouldn't kill the other
                rows = []
            for f in rows:
                key = f.xbrl_url or f"{f.symbol}|{f.period_end}|{f.filing_date}"
                if key in seen:
                    continue
                seen.add(key)
                out.append(f)
        return out

    def _fetch_legacy(self, since: date, symbol: str | None) -> list[FiledResult]:
        import json
        import urllib.parse
        url = _NSE_RESULTS_URL + (f"&symbol={urllib.parse.quote(symbol)}" if symbol else "")
        rows = json.loads(self._http(url))
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

    def _fetch_integrated(self, since: date, symbol: str | None) -> list[FiledResult]:
        """The Integrated Filing feed. Different row shape: `qe_Date` is the
        quarter end, `broadcast_Date` the filing timestamp, `xbrl` the doc URL."""
        import json
        import urllib.parse
        url = _NSE_INTEGRATED_URL + (f"&symbol={urllib.parse.quote(symbol)}" if symbol else "")
        rows = json.loads(self._http(url))
        if isinstance(rows, dict):
            rows = rows.get("data", [])
        out: list[FiledResult] = []
        for r in rows:
            try:
                xbrl = r.get("xbrl", "") or ""
                if not xbrl.lower().endswith(".xml"):
                    continue
                fd = _nse_date(r["broadcast_Date"])   # "24-Apr-2026 22:57:12"
                if fd < since:
                    continue
                out.append(FiledResult(
                    symbol=r["symbol"],
                    period_end=_nse_date(r["qe_Date"]),   # "31-MAR-2026"
                    filing_date=fd,
                    xbrl_url=xbrl,
                ))
            except (KeyError, ValueError):
                continue
        return out

    def fetch_xbrl(self, filed: FiledResult) -> bytes:
        if self._http is None or not filed.xbrl_url:
            raise RuntimeError("no live HTTP getter / XBRL url for this filing")
        return self._http(filed.xbrl_url)


def to_record(filed: FiledResult, *, eps_ttm: float, book_value_per_share: float,
              roe: float | None = None, net_profit: float | None = None,
              net_worth: float | None = None, total_debt: float | None = None,
              debt_to_equity: float | None = None) -> FundamentalRecord:
    """Build a point-in-time FundamentalRecord from a filing, dated by its
    filing_date (the only date a backtest may trust it from)."""
    return FundamentalRecord(
        symbol=filed.symbol,
        period_end=filed.period_end,
        publish_date=filed.filing_date,
        eps_ttm=eps_ttm,
        book_value_per_share=book_value_per_share,
        roe=roe,
        net_profit=net_profit,
        net_worth=net_worth,
        total_debt=total_debt,
        debt_to_equity=debt_to_equity,
    )


def build_record_from_financials(filed: FiledResult, fin: dict[str, float | None]) -> FundamentalRecord:
    """Build a FundamentalRecord from FiledResult and parsed financials,
    computing Net Worth, BVPS, Total Debt, and Debt-to-Equity automatically."""
    eps = fin.get("basic_eps")
    if eps is None:
        raise ValueError(f"Filing for {filed.symbol} {filed.period_end} lacks basic_eps")
        
    net_profit = float(fin["net_profit"]) if fin.get("net_profit") is not None else None
    eq_cap = float(fin["equity_capital"]) if fin.get("equity_capital") is not None else None
    face_val = float(fin["face_value"]) if fin.get("face_value") is not None else 10.0
    other_eq = float(fin["other_equity"]) if fin.get("other_equity") is not None else None
    
    # Net worth ONLY from real equity: the total-equity tag (consolidated:
    # EquityAttributableToOwnersOfParent), or share capital + other equity.
    # NOT share capital alone — a pure-quarterly filing carries no balance sheet
    # but still reports PaidUpValueOfEquityShareCapital, and using that as net
    # worth produced the alternation (ABB Rs 42cr share capital vs Rs 9,339cr
    # real equity, quarter by quarter). If neither is present, net worth is
    # simply absent for this filing; ROE/D-E fall back to the latest filing that
    # actually carries a balance sheet (typically H1 / annual).
    net_worth = None
    if fin.get("equity") is not None:
        net_worth = float(fin["equity"])
    elif eq_cap is not None and other_eq is not None:
        net_worth = eq_cap + other_eq

    bvps = 0.0
    if net_worth is not None and eq_cap is not None and eq_cap > 0 and face_val > 0:
        shares = eq_cap / face_val
        bvps = net_worth / shares
        
    long_debt = float(fin["noncurrent_borrowings"]) if fin.get("noncurrent_borrowings") is not None else 0.0
    short_debt = float(fin["current_borrowings"]) if fin.get("current_borrowings") is not None else 0.0
    total_debt = long_debt + short_debt
    if total_debt == 0.0 and fin.get("borrowings") is not None:
        total_debt = float(fin["borrowings"])
        
    has_debt_info = (fin.get("noncurrent_borrowings") is not None or 
                     fin.get("current_borrowings") is not None or 
                     fin.get("borrowings") is not None)
    if not has_debt_info:
        total_debt = None
        
    d2e = None
    if total_debt is not None and net_worth is not None and net_worth > 0:
        d2e = total_debt / net_worth

    revenue = float(fin["revenue"]) if fin.get("revenue") is not None else None

    return FundamentalRecord(
        symbol=filed.symbol,
        period_end=filed.period_end,
        publish_date=filed.filing_date,
        eps_ttm=float(eps),
        book_value_per_share=bvps,
        net_profit=net_profit,
        net_worth=net_worth,
        total_debt=total_debt,
        debt_to_equity=d2e,
        revenue=revenue,
    )
