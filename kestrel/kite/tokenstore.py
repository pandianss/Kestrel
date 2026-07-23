"""Where the day's access_token lives so every service can read it.

Doc 10 §2 calls for the login helper to "distribute the token to all services
(via Redis/secret store)." On a single host to start (doc 10 §3), a
restrictive-permission file is the secret store; the `TokenStore` protocol
keeps the shape so a `RedisTokenStore` can drop in later without touching the
login flow or the services.

Two rules this enforces:

  * **Never world-readable.** The file is created 0600. The access_token is a
    live order-placing credential; the static IP is the only *other* control
    stopping a leaked token (doc 10 §7), so the token file is treated as a
    secret, not a cache.

  * **Expiry is not the reader's problem to guess.** `load_valid(now)` returns
    the token only if it is still inside its 06:00-IST life; an expired token
    reads back as `None`, so a service that forgets to check still fails safe
    rather than sending orders Kite will reject with 403.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Protocol

from kestrel.kite.auth import TokenRecord


class TokenStore(Protocol):
    def save(self, token: TokenRecord) -> None: ...
    def load(self) -> TokenRecord | None: ...


class FileTokenStore:
    """Single-host secret store: one 0600 JSON file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, token: TokenRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Create with 0600 from the start so the token is never briefly
        # world-readable between write and chmod.
        fd = os.open(
            self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(asdict(token), f, indent=2)
        finally:
            try:
                os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass  # best-effort on filesystems without POSIX perms

    def load(self) -> TokenRecord | None:
        if not self.path.exists():
            return None
        return TokenRecord(**json.loads(self.path.read_text()))

    def load_valid(self, now: datetime) -> TokenRecord | None:
        """The token only if it is still valid at `now`; otherwise None so the
        caller fails safe and re-mints instead of sending doomed orders."""
        tok = self.load()
        if tok is None or not tok.is_valid(now):
            return None
        return tok
