"""Shared-secret gate + tiny in-memory rate limiter for the mutating web routes (Starlette).

The day-fetch POST triggers VirES fetch/export subprocesses on the host, so it is gated by a
shared secret. This module is a small, dependency-free auth layer:

- The secret is resolved at request time from the env var ``GEOMAG_API_TOKEN`` (if set and
  non-empty), else from the file named by the env var ``GEOMAG_API_TOKEN_FILE``
  (whitespace-stripped). There is no default file path. The secret is **never** baked into the
  repo or the served page.
- A request authenticates by sending the token in ``X-API-Token`` (or ``Authorization:
  Bearer <token>``); it is compared with ``hmac.compare_digest`` (constant time).
- FAIL CLOSED: if no token is configured at all, every gated route rejects.
- Rate limit per client IP: ``GEOMAG_RATE_LIMIT`` requests (default 10) per
  ``GEOMAG_RATE_WINDOW_S`` seconds (default 60).
"""
from __future__ import annotations

import hmac
import os
import time
from collections import deque
from pathlib import Path
from threading import Lock

RATE_LIMIT_MAX = int(os.environ.get("GEOMAG_RATE_LIMIT", "10"))
RATE_LIMIT_WINDOW_S = float(os.environ.get("GEOMAG_RATE_WINDOW_S", "60"))


def resolve_secret() -> str:
    """Return the configured shared secret, or '' if none is configured (env unset AND token
    file unset/missing/empty). Resolved fresh each call so a rotated token/file takes effect
    without a restart."""
    env = os.environ.get("GEOMAG_API_TOKEN")
    if env and env.strip():
        return env.strip()
    path = (os.environ.get("GEOMAG_API_TOKEN_FILE") or "").strip()
    if not path:
        return ""
    try:
        return Path(path).expanduser().read_text().strip()
    except OSError:
        return ""


def _presented(request) -> str:
    tok = request.headers.get("X-API-Token")
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
