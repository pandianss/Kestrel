"""Daily Kite login (doc 10 §2) — the operator-in-the-loop token mint.

Run this each trading morning before the data jobs. It is deliberately
semi-manual: you log in in your own browser (2FA/TOTP), then paste the
redirect back. Automating the browser login is the G-12 ToS gray area and is
NOT done here.

    export KITE_API_KEY=xxxx
    export KITE_API_SECRET=yyyy        # never commit these; env only (doc 10 §7)
    python scripts/kite_login.py

The access_token is written to data/secrets/kite_token.json (0600, gitignored)
and read by the data jobs. It is never printed. It expires at 06:00 IST, so
this is a once-a-day step.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kestrel.kite.auth import (
    KiteAuthError,
    exchange_request_token,
    extract_request_token,
    login_url,
)
from kestrel.kite.tokenstore import FileTokenStore

TOKEN_PATH = "data/secrets/kite_token.json"


def main() -> int:
    api_key = os.environ.get("KITE_API_KEY", "")
    api_secret = os.environ.get("KITE_API_SECRET", "")
    if not api_key or not api_secret:
        print("KITE_API_KEY / KITE_API_SECRET not set in the environment.")
        print("Set them first (doc 10 §7 — env only, never in code):")
        print("  export KITE_API_KEY=xxxx")
        print("  export KITE_API_SECRET=yyyy")
        return 2

    store = FileTokenStore(TOKEN_PATH)
    now = datetime.now(timezone.utc)

    existing = store.load_valid(now)
    if existing is not None:
        print(f"A valid token is already stored ({existing.masked()}).")
        print("Nothing to do — it is good until 06:00 IST. Delete the file to force a re-mint.")
        return 0

    print("Step 1 — open this URL in your browser and log in (2FA/TOTP):\n")
    print(f"    {login_url(api_key)}\n")
    print("Step 2 — after login your browser lands on your redirect URL.")
    print("Paste that FULL address (or just the request_token) here:\n")
    redirect = input("  redirect URL / request_token > ").strip()

    try:
        request_token = extract_request_token(redirect)
    except ValueError as e:
        print(f"\n✗ {e}")
        return 1

    try:
        token = exchange_request_token(api_key, api_secret, request_token, now=now)
    except (KiteAuthError, ValueError) as e:
        print(f"\n✗ login failed: {e}")
        return 1

    store.save(token)
    print(f"\n✓ token minted and stored at {TOKEN_PATH}")
    print(f"  {token.masked()}")
    print("  Data jobs can now run. This token dies at 06:00 IST; re-run tomorrow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
