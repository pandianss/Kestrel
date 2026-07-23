"""Kite Connect daily login — the request_token -> access_token exchange.

The `access_token` expires at 06:00 IST every day by regulation and there is
no refresh token (doc 02 §1, doc 10 §2), so a fresh token must be minted each
trading morning. This module is the mint.

Design constraints it honours:

  * **Operator-in-the-loop by default.** The redirect step needs a real Kite
    login (2FA TOTP). Automating it with a headless browser sits in a ToS gray
    area (G-12), so this helper stops at the boundary: it builds the login URL,
    the operator logs in in a browser, and pastes back the redirect. No
    credentials are ever typed into an automated flow here.

  * **Secrets stay in the environment (doc 10 §7).** `api_key`/`api_secret`
    are read from env vars, never hard-coded. The `access_token` is never
    printed or logged — only a masked confirmation and its expiry.

  * **Pure, testable core.** The checksum and expiry math are pure functions;
    the one network call is isolated behind an injectable `http` callable so
    the exchange is testable without touching Kite.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable

#: IST is UTC+5:30 year-round (no DST). Hard-coded to avoid a tzdata
#: dependency on Windows, where zoneinfo has no system database.
IST = timezone(timedelta(hours=5, minutes=30))

_KITE_LOGIN_BASE = "https://kite.zerodha.com/connect/login"
_KITE_SESSION_URL = "https://api.kite.trade/session/token"
_KITE_API_VERSION = "3"


class KiteAuthError(Exception):
    """The token exchange failed. Carries Kite's error message when available;
    never carries the access_token or the api_secret."""


@dataclass(frozen=True)
class TokenRecord:
    """A minted session. `access_token` is a live credential — do not log it."""
    api_key: str
    access_token: str
    user_id: str
    minted_at: str        # ISO-8601 UTC
    expires_at: str       # ISO-8601 UTC — next 06:00 IST after mint

    def is_valid(self, now: datetime) -> bool:
        """True while the token is still usable. Kite kills it at 06:00 IST."""
        return now < datetime.fromisoformat(self.expires_at)

    def masked(self) -> str:
        """A safe-to-print identity of the token — never the token itself."""
        tail = self.access_token[-4:] if len(self.access_token) >= 4 else "????"
        return f"user={self.user_id} token=…{tail} expires={self.expires_at}"


def login_url(api_key: str) -> str:
    """The URL the operator opens to log in. Contains only the api_key (public
    by Kite's design) — safe to print."""
    if not api_key:
        raise ValueError("api_key is empty — set KITE_API_KEY")
    return f"{_KITE_LOGIN_BASE}?v={_KITE_API_VERSION}&api_key={urllib.parse.quote(api_key)}"


def extract_request_token(redirect: str) -> str:
    """Pull `request_token` out of the URL Kite redirects to after login.

    Accepts either the full redirect URL (…?request_token=XXX&action=login&…)
    or a bare token pasted by the operator. The request_token is single-use and
    short-lived; it is not persisted."""
    redirect = redirect.strip()
    if "request_token=" in redirect:
        q = urllib.parse.urlparse(redirect).query
        vals = urllib.parse.parse_qs(q).get("request_token", [])
        if not vals or not vals[0]:
            raise ValueError("no request_token found in the redirect URL")
        return vals[0]
    # bare token
    if not redirect or "/" in redirect or "?" in redirect:
        raise ValueError(
            "could not read a request_token — paste the full redirect URL "
            "(the address bar after login) or just the token value"
        )
    return redirect


def checksum(api_key: str, request_token: str, api_secret: str) -> str:
    """Kite's login checksum: SHA-256 of (api_key + request_token + api_secret).

    A pure function of its inputs — the one place the api_secret is used, and
    it never leaves this process."""
    return hashlib.sha256(
        (api_key + request_token + api_secret).encode("utf-8")
    ).hexdigest()


def next_token_expiry(now: datetime) -> datetime:
    """The next 06:00 IST strictly after `now`, as a UTC datetime. That is when
    Kite expires the token regardless of when it was minted."""
    now_ist = now.astimezone(IST)
    six_ist = now_ist.replace(hour=6, minute=0, second=0, microsecond=0)
    if now_ist >= six_ist:
        six_ist = six_ist + timedelta(days=1)
    return six_ist.astimezone(timezone.utc)


def _default_http(url: str, data: bytes, headers: dict) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (fixed host)
        return resp.read()


def exchange_request_token(
    api_key: str,
    api_secret: str,
    request_token: str,
    *,
    now: datetime,
    http: Callable[[str, bytes, dict], bytes] = _default_http,
) -> TokenRecord:
    """Exchange a single-use request_token for a session (access_token).

    POSTs to Kite's session endpoint with the checksum. `now` is passed in
    (not read from the clock) so expiry is deterministic and testable. `http`
    is injectable so the exchange can be exercised without a network.
    """
    if not api_key or not api_secret:
        raise ValueError(
            "api_key/api_secret missing — set KITE_API_KEY and KITE_API_SECRET "
            "in the environment (never hard-code them; doc 10 §7)"
        )
    body = urllib.parse.urlencode(
        {
            "api_key": api_key,
            "request_token": request_token,
            "checksum": checksum(api_key, request_token, api_secret),
        }
    ).encode("utf-8")
    headers = {
        "X-Kite-Version": _KITE_API_VERSION,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        raw = http(_KITE_SESSION_URL, body, headers)
    except urllib.error.HTTPError as e:  # Kite returns JSON error bodies
        detail = _error_detail(e.read())
        raise KiteAuthError(f"token exchange rejected by Kite: {detail}") from None
    except urllib.error.URLError as e:
        raise KiteAuthError(f"could not reach Kite session endpoint: {e.reason}") from None

    payload = json.loads(raw)
    data = payload.get("data") or {}
    access_token = data.get("access_token")
    if not access_token:
        raise KiteAuthError(f"Kite response had no access_token: {payload!r}")

    return TokenRecord(
        api_key=api_key,
        access_token=access_token,
        user_id=data.get("user_id", ""),
        minted_at=now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        expires_at=next_token_expiry(now).isoformat(timespec="seconds"),
    )


def _error_detail(raw: bytes) -> str:
    try:
        return json.loads(raw).get("message", raw.decode("utf-8", "replace"))
    except (ValueError, AttributeError):
        return raw.decode("utf-8", "replace")[:200]
