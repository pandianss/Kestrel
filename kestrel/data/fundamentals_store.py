"""Point-in-time fundamentals store — where filed results accumulate.

Company results arrive over time (each quarter, ~45 days after period end), and
a result can be **restated** later. Both facts make this a point-in-time
problem, not a table of "current" numbers:

  * A record is keyed by (symbol, period_end, **publish_date**). The original
    filing and a later restatement of the same quarter are *both* kept, with
    different publish_dates — so a backtest as of an old date sees the number
    that was public *then*, not the restated one (the look-ahead guard that
    `fundamentals.py` defines and `value`/`quality` rely on).

  * Append-only and immutable (D-15): re-ingesting the same filing is a no-op;
    a *different* value under an identical (symbol, period_end, publish_date)
    key raises rather than overwriting — that would be silent history rewriting.

The store implements the `FundamentalsSource` protocol (`asof`), so the value
and quality factors read straight from it. On disk: one JSONL file per symbol
under `data/fundamentals/`, so a new filing is one appended line.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from kestrel.data.fundamentals import FundamentalRecord


class FundamentalsConflictError(Exception):
    """A different value under an existing (symbol, period_end, publish_date)
    key — D-15 refusing to rewrite a filing already recorded."""


def _to_json(r: FundamentalRecord) -> str:
    d = asdict(r)
    d["period_end"] = r.period_end.isoformat()
    d["publish_date"] = r.publish_date.isoformat()
    return json.dumps(d, sort_keys=True)


def _from_json(line: str) -> FundamentalRecord:
    d = json.loads(line)
    d["period_end"] = date.fromisoformat(d["period_end"])
    d["publish_date"] = date.fromisoformat(d["publish_date"])
    return FundamentalRecord(**d)


class FundamentalsStore:
    def __init__(self, root: str | Path = "data/fundamentals"):
        self.root = Path(root)
        # Per-symbol in-memory cache. A factor backtest calls asof() for every
        # (date, symbol) cell — tens of thousands of times — so re-reading the
        # file per call would be O(N·M) disk reads. Lazy-load once per symbol and
        # keep the cache fresh on add(). Per-instance; single-process by design.
        self._cache: dict[str, list[FundamentalRecord]] = {}
        self._attempted: set[tuple[str, str, str]] | None = None   # negative cache

    def _path(self, symbol: str) -> Path:
        return self.root / f"{symbol}.jsonl"

    # ---- negative cache: filings tried that yielded no record -----------
    # Some filings deterministically produce nothing (no current-quarter EPS, or
    # an ambiguous context layout). Without remembering them, a re-run re-fetches
    # every one of them each cycle — pure wasted network. This records them so
    # they are skipped next time. (An amendment gets a new publish_date, hence a
    # new key, so it is NOT skipped.)
    def _attempted_path(self) -> Path:
        return self.root / "_attempted.jsonl"

    def _load_attempted(self) -> set[tuple[str, str, str]]:
        if self._attempted is None:
            p = self._attempted_path()
            self._attempted = set()
            if p.exists():
                for ln in p.read_text(encoding="utf-8").splitlines():
                    parts = ln.strip().split("|")
                    if len(parts) == 3:
                        self._attempted.add((parts[0], parts[1], parts[2]))
        return self._attempted

    def was_attempted(self, symbol: str, period_end: date, publish_date: date) -> bool:
        return (symbol, period_end.isoformat(), publish_date.isoformat()) in self._load_attempted()

    def mark_attempted(self, symbol: str, period_end: date, publish_date: date) -> None:
        key = (symbol, period_end.isoformat(), publish_date.isoformat())
        if key in self._load_attempted():
            return
        self._attempted.add(key)
        self.root.mkdir(parents=True, exist_ok=True)
        with self._attempted_path().open("a", encoding="utf-8") as f:
            f.write("|".join(key) + "\n")

    def _load(self, symbol: str) -> list[FundamentalRecord]:
        cached = self._cache.get(symbol)
        if cached is not None:
            return cached
        recs: list[FundamentalRecord] = []
        p = self._path(symbol)
        if p.exists():
            for ln in p.read_text(encoding="utf-8").splitlines():
                if not ln.strip():
                    continue
                try:
                    recs.append(_from_json(ln))
                except (json.JSONDecodeError, ValueError, KeyError):
                    # A partial line from a concurrent write, or a corrupt line —
                    # skip it rather than crash the whole read. Don't cache a
                    # partial read as complete if we hit one.
                    continue
        self._cache[symbol] = recs
        return recs

    def add(self, record: FundamentalRecord) -> bool:
        """Append `record` unless it already exists. Returns True if written,
        False if it was already present (idempotent). Raises on a conflicting
        value for an identical key."""
        existing = self._load(record.symbol)
        key = (record.period_end, record.publish_date)
        for e in existing:
            if (e.period_end, e.publish_date) == key:
                if _to_json(e) == _to_json(record):
                    return False   # idempotent re-ingest
                raise FundamentalsConflictError(
                    f"{record.symbol} {record.period_end} filed {record.publish_date}: "
                    f"a different value is already recorded — refusing to rewrite (D-15). "
                    f"A restatement must carry a later publish_date."
                )
        self.root.mkdir(parents=True, exist_ok=True)
        with self._path(record.symbol).open("a", encoding="utf-8") as f:
            f.write(_to_json(record) + "\n")
        existing.append(record)   # keep the cache fresh (same list object as cached)
        return True

    def has(self, symbol: str, period_end: date, publish_date: date) -> bool:
        """True if this exact filing is already stored — lets a harvest resume
        without re-fetching what it already has."""
        key = (period_end, publish_date)
        return any((e.period_end, e.publish_date) == key for e in self._load(symbol))

    def asof(self, symbol: str, d: date) -> FundamentalRecord | None:
        """FundamentalsSource: the latest record for `symbol` that was public on
        or before `d` (by publish_date)."""
        public = [r for r in self._load(symbol) if r.publish_date <= d]
        if not public:
            return None
        return max(public, key=lambda r: r.publish_date)

    def has_period(self, symbol: str, period_end: date) -> bool:
        """True if any record for this (symbol, period_end) exists — lets the
        history backfill skip a quarter it already has without re-fetching both
        the standalone and consolidated filings for it."""
        return any(e.period_end == period_end for e in self._load(symbol))

    def records(self, symbol: str) -> list[FundamentalRecord]:
        """All stored records for `symbol` (any period), for trend analysis.
        Returns a copy so callers can't mutate the cache."""
        return list(self._load(symbol))

    def symbols(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("*.jsonl"))
