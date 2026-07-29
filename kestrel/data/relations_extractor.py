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
  * **NSE shareholding-pattern master** → the **promoter & promoter-group**
    aggregate holding %, per quarter, dated by the disclosure (broadcast) date —
    the verifiable corporate-control relationship and its trend.

Deliberately NOT emitted (no verifiable free structured source):
  * **Named subsidiaries** and individual promoter entities — annual-report
    AOC-1 and the detailed shareholding XBRL are deeper/unstructured; only the
    promoter *aggregate* is taken here, never a fabricated corporate tree.
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
from kestrel.data.relations import CorporateRelation, IndustryMapping, ProductSegment, RelationType
from kestrel.data.relations_store import RelationsStore

_SHP_URL = "https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol={symbol}"


def _nse_upper_date(s: str):
    """NSE shareholding dates come UPPER-cased ('30-JUN-2026'); title-case the
    month so strptime accepts it."""
    from datetime import datetime
    return datetime.strptime(s.strip().split(" ")[0].title(), "%d-%b-%Y").date()


def extract_promoter_relations(symbol: str, rows: list[dict], *, source: str) -> list[CorporateRelation]:
    """Verifiable promoter & promoter-group holding per quarter, from NSE's
    shareholding-pattern master (`pr_and_prgrp`). Dated by the broadcast date
    (when it became public) — point-in-time safe. One relation per disclosure."""
    out: list[CorporateRelation] = []
    seen: set = set()
    for r in rows:
        pct = r.get("pr_and_prgrp")
        pub = r.get("broadcastDate") or r.get("date")
        if pct is None or pub is None:
            continue
        try:
            frac = float(pct) / 100.0
            pd_ = _nse_upper_date(pub)
        except (ValueError, TypeError):
            continue
        if not (0.0 <= frac <= 1.0) or pd_ in seen:
            continue
        seen.add(pd_)
        out.append(CorporateRelation(
            source_symbol=symbol,
            target_name_or_symbol="Promoter & Promoter Group",
            relation_type=RelationType.PROMOTER_GROUP,
            holding_pct=round(frac, 6),
            publish_date=pd_,
            source=source,
        ))
    return out


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
                             *, industry: str | None = None,
                             shareholding_rows: list[dict] | None = None) -> dict[str, int]:
    """Populate `store` for one symbol from verifiable sources. Returns counts.

    `relations` comes from the shareholding-pattern master (promoter holding %)
    when `shareholding_rows` is supplied — the one verifiable corporate-control
    source. Named subsidiaries are still not emitted (no verifiable free feed)."""
    added = {"relations": 0, "segments": 0, "industry": 0}

    if shareholding_rows is not None:
        src = _SHP_URL.format(symbol=symbol)
        for rel in extract_promoter_relations(symbol, shareholding_rows, source=src):
            try:
                if store.add_relation(rel):
                    added["relations"] += 1
            except Exception:  # noqa: BLE001 — conflict/validation; skip one
                pass

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


def _fetch_shareholding(getter, symbol: str) -> list[dict] | None:
    """Fetch the shareholding-pattern master rows for `symbol`, or None on any
    failure (relations are optional; a fetch error must not sink the profile)."""
    import json
    try:
        d = json.loads(getter(_SHP_URL.format(symbol=symbol)))
        return d if isinstance(d, list) else d.get("data", [])
    except Exception:  # noqa: BLE001
        return None


def _is_fresh(store: RelationsStore, symbol: str, refresh_days: int) -> bool:
    """True if this symbol was processed within refresh_days — so a re-run skips
    it without re-downloading. Checks ANY of the three outputs (a single-segment
    company writes no segments file but does write promoter/industry), so a
    symbol that produced *something* is not needlessly re-fetched."""
    import time
    paths = [store._relations_path(symbol), store._segments_path(symbol),
             store._industry_path(symbol)]
    mtimes = [p.stat().st_mtime for p in paths if p.exists()]
    if not mtimes:
        return False
    return (time.time() - max(mtimes)) / 86400.0 < refresh_days


def harvest_all_relations(fundamentals_root: str | Path = "data/fundamentals",
                          relations_root: str | Path = "data/relations",
                          *, source=None, industry=None, symbols=None,
                          shareholding_getter=None, refresh_days=7, log=print) -> dict[str, int]:
    """Refresh verifiable company reference data for the symbols in the
    fundamentals store: segments + industry from the filing/NSE, and promoter
    holding % from the shareholding-pattern master. Resumable: a symbol
    refreshed within `refresh_days` is skipped. Returns counts (keys the worker
    logs)."""
    if symbols is None:
        symbols = FundamentalsStore(fundamentals_root).symbols()
    store = RelationsStore(relations_root)
    pending = [s for s in symbols if not _is_fresh(store, s, refresh_days)]
    if not pending:
        return {"symbols_processed": 0, "relations_added": 0, "segments_added": 0, "industry_added": 0}
    if source is None or shareholding_getter is None:
        from kestrel.data.nse_http import make_nse_getter
        getter = make_nse_getter()
        source = source or NSEFilingsSource(http=getter)
        shareholding_getter = shareholding_getter or getter
    if industry is None:
        industry = industry_map()

    tot = {"symbols_processed": 0, "relations_added": 0, "segments_added": 0, "industry_added": 0}
    n = len(pending)
    log(f"  {n} symbol(s) to process (each pulls filings + shareholding + segments) ...")
    for i, sym in enumerate(pending, 1):
        try:
            filings = source.recent(date(2000, 1, 1), symbol=sym)
            shp = _fetch_shareholding(shareholding_getter, sym)
            c = extract_symbol_relations(sym, filings, source.fetch_xbrl, store,
                                         industry=industry.get(sym), shareholding_rows=shp)
        except Exception as e:  # noqa: BLE001
            log(f"  {sym}: relations error: {e}")
            continue
        tot["symbols_processed"] += 1
        tot["relations_added"] += c["relations"]
        tot["segments_added"] += c["segments"]
        tot["industry_added"] += c["industry"]
        if i % 10 == 0 or i == n:
            log(f"  … {i}/{n}  {sym:<12} (+{tot['relations_added']} rel, "
                f"+{tot['segments_added']} seg, +{tot['industry_added']} ind)")
    return tot
