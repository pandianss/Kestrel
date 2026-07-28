"""Verifiable company reference-data ingestion — industry & business segments.

⚠️ **This module ingests only what an authoritative source ASSERTS, with the
source recorded.** It does not infer, recall, or guess. An earlier version of
this file hard-coded sectors/subsidiaries/segment-splits from model knowledge
and even assigned an industry from a hash of the ticker; that is exactly the
un-verifiable approach the project forbids, and it has been removed.

Sources (each recorded on the record's `source`):
  * **Results XBRL** (the company's own filing) → the list of **reportable
    business segments** (`DescriptionOfReportableSegment`) and their **revenue
    share** (`SegmentRevenue`, normalised over positive segment revenue). Real,
    filed numbers — not guesses.
  * **NSE index-constituents CSV** → NSE's **industry** classification.

Deliberately NOT emitted (no verifiable free structured source):
  * **Named subsidiaries / parent + holding %** — annual-report AOC-1 is
    unstructured and NSE's shareholding API is access-gated. `CorporateRelation`
    stays in the model for a future authoritative source, but nothing is written
    here rather than fabricate a corporate tree.
  * **Products, granular sub-sectors** — left blank, never invented.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Callable

from kestrel.data.filings import NSEFilingsSource, report_basis
from kestrel.data.fundamentals_store import FundamentalsStore
from kestrel.data.relations import IndustryMapping, ProductSegment
from kestrel.data.relations_store import RelationsStore


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def extract_segments(xbrl_bytes: bytes) -> list[tuple[str, float]]:
    """(segment_name, revenue_share) from a results XBRL, from the filing's own
    `SegmentRevenue` facts. A segment reports revenue under several contexts
    (quarter, YTD, prior periods); we take each segment's largest positive
    figure (a consistent reporting-period basis) and normalise to shares that
    sum to 1. Empty if the filing discloses no segment revenue."""
    root = ET.parse(io.BytesIO(xbrl_bytes)).getroot()
    ctx_name: dict[str, str] = {}
    ctx_rev: dict[str, float] = {}
    for el in root.iter():
        c = el.get("contextRef")
        if not c or not el.text or not el.text.strip():
            continue
        ln = _local(el.tag)
        if ln == "DescriptionOfReportableSegment":
            ctx_name[c] = el.text.strip()
        elif ln in ("SegmentRevenue", "SegmentRevenueFromOperations"):
            try:
                ctx_rev[c] = float(el.text)
            except ValueError:
                pass
    best: dict[str, float] = {}
    for c, name in ctx_name.items():
        rev = ctx_rev.get(c)
        if rev is not None and rev > 0:
            best[name] = max(best.get(name, 0.0), rev)
    total = sum(best.values())
    if total <= 0:
        return []
    return sorted(((n, r / total) for n, r in best.items()), key=lambda x: -x[1])


def industry_map(indices=("nifty500",), *, http: Callable[[str], bytes] | None = None
                 ) -> dict[str, str]:
    """symbol -> NSE industry classification, from index-constituents CSVs."""
    import csv

    from kestrel.data.constituents import INDEX_CSV
    if http is None:
        from kestrel.data.nse_http import make_nse_getter
        http = make_nse_getter()
    out: dict[str, str] = {}
    for idx in indices:
        try:
            rows = csv.DictReader(io.StringIO(http(INDEX_CSV[idx]).decode("utf-8-sig")))
            for r in rows:
                sym = (r.get("Symbol") or "").strip()
                ind = (r.get("Industry") or "").strip()
                if sym and ind and sym not in out:
                    out[sym] = ind
        except Exception:  # noqa: BLE001
            continue
    return out


def _latest_consolidated(filings, fetch_xbrl):
    """The newest filing's XBRL, preferring the consolidated one (fuller
    segments). Returns (xbrl_bytes, filing) or (None, None)."""
    if not filings:
        return None, None
    latest_pe = max(f.period_end for f in filings)
    latest = [f for f in filings if f.period_end == latest_pe][:2]
    std = None
    for f in latest:
        try:
            xb = fetch_xbrl(f)
        except Exception:  # noqa: BLE001
            continue
        if report_basis(xb) == "consolidated":
            return xb, f
        std = std or (xb, f)
    return std if std else (None, None)


def extract_symbol_relations(symbol, filings, fetch_xbrl, store: RelationsStore,
                             *, industry: str | None = None) -> dict[str, int]:
    """Populate `store` for one symbol from verifiable sources. Returns counts.
    `relations` is always 0 — named corporate relations have no verifiable free
    source, so none are fabricated."""
    added = {"relations": 0, "segments": 0, "industry": 0}
    xb, filed = _latest_consolidated(filings, fetch_xbrl)
    if xb is None or filed is None:
        return added

    pe, pub = filed.period_end, max(filed.filing_date, filed.period_end)
    src = filed.xbrl_url

    for name, pct in extract_segments(xb):
        seg = ProductSegment(symbol=symbol, segment_name=name, revenue_pct=round(pct, 6),
                             period_end=pe, publish_date=pub, source=src)
        if store.add_segment(seg):
            added["segments"] += 1

    if industry:
        im = IndustryMapping(symbol=symbol, primary_industry=industry, sub_sector="",
                             related_industries=[], effective_from=pub,
                             source="nse:indices/constituents")
        if store.add_industry(im):
            added["industry"] += 1
    return added


def _is_fresh(store: RelationsStore, symbol: str, refresh_days: int) -> bool:
    """True if this symbol's segments were refreshed within refresh_days — so the
    harvest can skip it without re-downloading (segments change ~quarterly)."""
    import time
    p = store._segments_path(symbol)
    if not p.exists():
        return False
    return (time.time() - p.stat().st_mtime) / 86400.0 < refresh_days


def harvest_all_relations(fundamentals_root: str | Path = "data/fundamentals",
                          relations_root: str | Path = "data/relations",
                          *, source=None, industry=None, symbols=None,
                          refresh_days=7, log=print) -> dict[str, int]:
    """Refresh verifiable company reference data for the symbols in the
    fundamentals store. Reads each company's latest filing (segments) and NSE's
    industry classification. Resumable: a symbol refreshed within `refresh_days`
    is skipped (no re-download). Returns counts (keys the worker logs)."""
    if symbols is None:
        symbols = FundamentalsStore(fundamentals_root).symbols()
    store = RelationsStore(relations_root)
    pending = [s for s in symbols if not _is_fresh(store, s, refresh_days)]
    if not pending:
        return {"symbols_processed": 0, "relations_added": 0, "segments_added": 0, "industry_added": 0}
    if source is None:
        from kestrel.data.nse_http import make_nse_getter
        source = NSEFilingsSource(http=make_nse_getter())
    if industry is None:
        industry = industry_map()

    tot = {"symbols_processed": 0, "relations_added": 0, "segments_added": 0, "industry_added": 0}
    for sym in pending:
        try:
            filings = source.recent(date(2000, 1, 1), symbol=sym)
            c = extract_symbol_relations(sym, filings, source.fetch_xbrl, store,
                                         industry=industry.get(sym))
        except Exception as e:  # noqa: BLE001
            log(f"  {sym}: relations error: {e}")
            continue
        tot["symbols_processed"] += 1
        tot["relations_added"] += c["relations"]
        tot["segments_added"] += c["segments"]
        tot["industry_added"] += c["industry"]
    return tot
