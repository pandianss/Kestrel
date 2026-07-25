"""A reusable NSE session getter.

NSE's public JSON/CSV endpoints reject bare requests — they need browser-like
headers and a session cookie seeded from a normal page first. This centralises
that dance (previously hand-rolled per source) into one factory. Real sources
accept an injected getter so they stay testable offline; this supplies the real
one on-host.

Not a scraper of anything private — these are NSE's own public corporate-filings,
index-constituents, and corporate-actions endpoints.
"""
from __future__ import annotations

import http.cookiejar
import urllib.request
from typing import Callable

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
_SEED = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"


def make_nse_getter(
    *, seed_url: str = _SEED, timeout: int = 30
) -> Callable[[str], bytes]:
    """Return a `get(url) -> bytes` that seeds cookies once, then fetches with
    browser headers. Cookies persist across calls on the returned closure."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    seeded = {"done": False}

    def _open(url: str, accept: str) -> bytes:
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": seed_url,
        })
        return opener.open(req, timeout=timeout).read()

    def get(url: str) -> bytes:
        if not seeded["done"]:
            try:
                _open(seed_url, "text/html")
            except Exception:  # noqa: BLE001 — seeding is best-effort
                pass
            seeded["done"] = True
        accept = "text/csv,*/*" if url.lower().endswith(".csv") else "application/json, text/plain, */*"
        return _open(url, accept)

    return get
