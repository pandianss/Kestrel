"""Immutable archive of the RAW filing documents (XBRL), keyed by their source.

D-15 (no destruction of data): the fundamentals store keeps *derived* numbers
(EPS, net worth, …), but the parser evolves — every calibration fix would
otherwise force a full re-fetch. Keeping the original XBRL means:

  * **reprocess without re-fetching** — a parser fix re-reads the archive
    locally (no network, no NSE load);
  * **provenance / audit** — the exact document a number came from;
  * **resilience** — NSE can rewrite or remove a filing later; the as-filed
    copy survives.

Layout: `data/filings_raw/<symbol>/<nse-filename>.xml`. NSE's XBRL filename is
already unique per filing, so it doubles as the key and dedups naturally. Write
once, never overwrite (the as-filed bytes are immutable).
"""
from __future__ import annotations

from pathlib import Path


class FilingArchive:
    def __init__(self, root: str | Path = "data/filings_raw"):
        self.root = Path(root)

    def _path(self, symbol: str, xbrl_url: str) -> Path:
        base = (xbrl_url.rsplit("/", 1)[-1] or "unknown").strip() or "unknown.xml"
        return self.root / symbol / base

    def has(self, symbol: str, xbrl_url: str) -> bool:
        return self._path(symbol, xbrl_url).exists()

    def read(self, symbol: str, xbrl_url: str) -> bytes | None:
        p = self._path(symbol, xbrl_url)
        return p.read_bytes() if p.exists() else None

    def write(self, symbol: str, xbrl_url: str, content: bytes) -> Path:
        """Persist the raw document once. If it already exists it is left as-is
        (immutable — the as-filed bytes don't change)."""
        p = self._path(symbol, xbrl_url)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        return p


def get_xbrl(archive: FilingArchive, source, symbol: str, filed) -> tuple[bytes, bool]:
    """Return the filing's XBRL, preferring the archive. On a miss, fetch it and
    archive the original before returning. Returns (bytes, from_archive) — so a
    re-run (or a reprocess) reads locally and never re-hits NSE for a document we
    already have."""
    cached = archive.read(symbol, filed.xbrl_url)
    if cached is not None:
        return cached, True
    xb = source.fetch_xbrl(filed)
    archive.write(symbol, filed.xbrl_url, xb)
    return xb, False
