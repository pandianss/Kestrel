"""Look-ahead safe corporate relations, segments, and industry stores.

Stored as JSONL on disk to preserve all history under append-only,
idempotent, and conflict-preventing rules (D-15).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from kestrel.data.relations import CorporateRelation, IndustryMapping, ProductSegment, RelationType


class RelationsConflictError(Exception):
    """Raised when writing a different value under an identical key (D-15)."""
    pass


def _relation_to_json(r: CorporateRelation) -> str:
    d = asdict(r)
    d["relation_type"] = r.relation_type.value
    d["publish_date"] = r.publish_date.isoformat()
    return json.dumps(d, sort_keys=True)


def _relation_from_json(line: str) -> CorporateRelation:
    d = json.loads(line)
    return CorporateRelation(
        source_symbol=d["source_symbol"],
        target_name_or_symbol=d["target_name_or_symbol"],
        relation_type=RelationType(d["relation_type"]),
        holding_pct=d["holding_pct"],
        publish_date=date.fromisoformat(d["publish_date"]),
    )


def _segment_to_json(s: ProductSegment) -> str:
    d = asdict(s)
    d["period_end"] = s.period_end.isoformat()
    d["publish_date"] = s.publish_date.isoformat()
    return json.dumps(d, sort_keys=True)


def _segment_from_json(line: str) -> ProductSegment:
    d = json.loads(line)
    return ProductSegment(
        symbol=d["symbol"],
        segment_name=d["segment_name"],
        revenue_pct=d["revenue_pct"],
        period_end=date.fromisoformat(d["period_end"]),
        publish_date=date.fromisoformat(d["publish_date"]),
        source=d.get("source", ""),
    )


def _industry_to_json(m: IndustryMapping) -> str:
    d = asdict(m)
    d["effective_from"] = m.effective_from.isoformat()
    return json.dumps(d, sort_keys=True)


def _industry_from_json(line: str) -> IndustryMapping:
    d = json.loads(line)
    return IndustryMapping(
        symbol=d["symbol"],
        primary_industry=d["primary_industry"],
        sub_sector=d["sub_sector"],
        related_industries=d["related_industries"],
        effective_from=date.fromisoformat(d["effective_from"]),
        source=d.get("source", ""),
    )


class RelationsStore:
    def __init__(self, root: str | Path = "data/relations"):
        self.root = Path(root)

    def _relations_path(self, symbol: str) -> Path:
        return self.root / "relations" / f"{symbol}.jsonl"

    def _segments_path(self, symbol: str) -> Path:
        return self.root / "segments" / f"{symbol}.jsonl"

    def _industry_path(self, symbol: str) -> Path:
        return self.root / "industry" / f"{symbol}.jsonl"

    # ---- write ---------------------------------------------------------
    def add_relation(self, r: CorporateRelation) -> bool:
        """Append a corporate relation unless it already exists.

        Returns True if written, False if already present (idempotent).
        Raises RelationsConflictError if a conflict is found.
        """
        path = self._relations_path(r.source_symbol)
        existing = []
        if path.exists():
            existing = [_relation_from_json(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]

        key = (r.target_name_or_symbol, r.relation_type, r.publish_date)
        for e in existing:
            if (e.target_name_or_symbol, e.relation_type, e.publish_date) == key:
                if _relation_to_json(e) == _relation_to_json(r):
                    return False
                raise RelationsConflictError(
                    f"Conflict for {r.source_symbol} -> {r.target_name_or_symbol} on {r.publish_date}"
                )

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(_relation_to_json(r) + "\n")
        return True

    def add_segment(self, s: ProductSegment) -> bool:
        """Append a segment unless it already exists.

        Returns True if written, False if already present (idempotent).
        Raises RelationsConflictError if a conflict is found.
        """
        path = self._segments_path(s.symbol)
        existing = []
        if path.exists():
            existing = [_segment_from_json(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]

        key = (s.segment_name, s.period_end, s.publish_date)
        for e in existing:
            if (e.segment_name, e.period_end, e.publish_date) == key:
                if _segment_to_json(e) == _segment_to_json(s):
                    return False
                raise RelationsConflictError(
                    f"Conflict for {s.symbol} segment '{s.segment_name}' on {s.publish_date}"
                )

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(_segment_to_json(s) + "\n")
        return True

    def add_industry(self, m: IndustryMapping) -> bool:
        """Append/update an industry mapping unless it already exists.

        Returns True if written, False if already present (idempotent).
        Raises RelationsConflictError if a conflict is found.
        """
        path = self._industry_path(m.symbol)
        existing = []
        if path.exists():
            existing = [_industry_from_json(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]

        key = m.effective_from
        for e in existing:
            if e.effective_from == key:
                if _industry_to_json(e) == _industry_to_json(m):
                    return False
                raise RelationsConflictError(
                    f"Conflict for {m.symbol} industry mapping on {m.effective_from}"
                )

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(_industry_to_json(m) + "\n")
        return True

    # ---- read (look-ahead safe) ----------------------------------------
    def relations_asof(self, symbol: str, d: date) -> list[CorporateRelation]:
        path = self._relations_path(symbol)
        if not path.exists():
            return []
        all_recs = [_relation_from_json(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]
        public = [r for r in all_recs if r.publish_date <= d]
        
        # Keep only the latest relation for each unique (target, type)
        latest: dict[tuple[str, RelationType], CorporateRelation] = {}
        for r in public:
            key = (r.target_name_or_symbol, r.relation_type)
            if key not in latest or r.publish_date > latest[key].publish_date:
                latest[key] = r
        return list(latest.values())

    def segments_asof(self, symbol: str, d: date) -> list[ProductSegment]:
        """Returns the segment breakdown for the latest financial period public on or before d."""
        path = self._segments_path(symbol)
        if not path.exists():
            return []
        all_recs = [_segment_from_json(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]
        public = [s for s in all_recs if s.publish_date <= d]
        if not public:
            return []

        # Resolve latest restatement for each (segment, period_end)
        resolved: dict[tuple[str, date], ProductSegment] = {}
        for s in public:
            key = (s.segment_name, s.period_end)
            if key not in resolved or s.publish_date > resolved[key].publish_date:
                resolved[key] = s

        # Find the latest available period_end
        if not resolved:
            return []
        max_pe = max(s.period_end for s in resolved.values())

        # Return only the segments for that period
        return [s for s in resolved.values() if s.period_end == max_pe]

    def industry_asof(self, symbol: str, d: date) -> IndustryMapping | None:
        path = self._industry_path(symbol)
        if not path.exists():
            return None
        all_recs = [_industry_from_json(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]
        public = [m for m in all_recs if m.effective_from <= d]
        if not public:
            return None
        return max(public, key=lambda m: m.effective_from)

    def symbols(self) -> list[str]:
        # Return unique symbols across relations, segments, and industry directories
        syms = set()
        for subdir in ("relations", "segments", "industry"):
            p = self.root / subdir
            if p.exists():
                syms.update(f.stem for f in p.glob("*.jsonl"))
        return sorted(list(syms))
