"""Shared-secret gate + tiny in-memory rate limiter for the mutating web routes (Starlette).

Foundry-wide hardening (REVIEW #6): the day-fetch POST (which triggers host VirES fetch/export
subprocesses) used to be ungated ("gate at nginx" — never actually enforced). This adds a uniform,
dependency-free auth layer:

- The secret is resolved at request time from the env var ``FOUNDRY_API_TOKEN`` (if set and
  non-empty), else from the file ``~/.config/foundry/api-token`` (whitespace-stripped). It is
  **never** baked into the repo or the served page.
- A request authenticates by sending the token in ``X-Foundry-Token`` (or ``Authorization:
  Bearer <token>``); it is compared with ``hmac.compare_digest`` (constant time).
- FAIL CLOSED: if no token is configured at all, every gated route rejects.

This small module is intentionally duplicated per repo (the foundry repos are independent — no
cross-repo package).
"""
from __future__ import annotations

import hmac
import os
import time
from collections import deque
from pathlib import Path
from threading import Lock

RATE_LIMIT_MAX = int(os.environ.get("FOUNDRY_RATE_LIMIT", "10"))
RATE_LIMIT_WINDOW_S = float(os.environ.get("FOUNDRY_RATE_WINDOW_S", "60"))

_TOKEN_FILE = Path.home() / ".config" / "foundry" / "api-token"


def resolve_secret() -> str:
    """Return the configured shared secret, or '' if none is configured (env unset AND file
    missing/empty). Resolved fresh each call so a rotated token/file takes effect without a restart."""
    env = os.environ.get("FOUNDRY_API_TOKEN")
    if env and env.strip():
        return env.strip()
    try:
        return _TOKEN_FILE.read_text().strip()
    except OSError:
        return ""


def _presented(request) -> str:
    tok = request.headers.get("X-Foundry-Token")
    if tok and tok.strip():
        return tok.strip()
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def check_token(request) -> bool:
    """True iff a valid token is presented on the Starlette request. Fails closed when no secret
    is configured."""
    secret = resolve_secret()
    if not secret:
        return False
    presented = _presented(request)
    if not presented:
        return False
    return hmac.compare_digest(presented, secret)


class RateLimiter:
    """Fixed-window-ish per-key limiter (a sliding deque of timestamps). Dependency-free,
    thread-safe, in-memory (a restart clears it — acceptable for this threat model)."""

    def __init__(self, max_requests: int = RATE_LIMIT_MAX, window_s: float = RATE_LIMIT_WINDOW_S):
        self.max_requests = max_requests
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._hits.setdefault(key, deque())
            while dq and dq[0] <= now - self.window_s:
                dq.popleft()
            if len(dq) >= self.max_requests:
                return False
            dq.append(now)
            return True
