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

    def _path(self, symbol: str) -> Path:
        return self.root / f"{symbol}.jsonl"

    def _load(self, symbol: str) -> list[FundamentalRecord]:
        p = self._path(symbol)
        if not p.exists():
            return []
        return [_from_json(ln) for ln in p.read_text().splitlines() if ln.strip()]

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
        return True

    def asof(self, symbol: str, d: date) -> FundamentalRecord | None:
        """FundamentalsSource: the latest record for `symbol` that was public on
        or before `d` (by publish_date)."""
        public = [r for r in self._load(symbol) if r.publish_date <= d]
        if not public:
            return None
        return max(public, key=lambda r: r.publish_date)

    def symbols(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("*.jsonl"))
