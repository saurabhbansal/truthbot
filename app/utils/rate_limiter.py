"""Simple in-memory rate limiter per phone number."""

from __future__ import annotations

import time
from collections import defaultdict

MAX_REQUESTS_PER_MINUTE = 5
WINDOW_SECONDS = 60
_CLEANUP_INTERVAL = 300


class RateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    def is_allowed(self, phone: str) -> bool:
        """Check if a phone number is within rate limits."""
        now = time.time()
        self._maybe_cleanup(now)

        window_start = now - WINDOW_SECONDS
        self._requests[phone] = [
            t for t in self._requests[phone] if t > window_start
        ]

        if len(self._requests[phone]) >= MAX_REQUESTS_PER_MINUTE:
            return False

        self._requests[phone].append(now)
        return True

    def remaining(self, phone: str) -> int:
        """Return how many requests remain in the current window."""
        now = time.time()
        window_start = now - WINDOW_SECONDS
        self._requests[phone] = [
            t for t in self._requests[phone] if t > window_start
        ]
        return max(0, MAX_REQUESTS_PER_MINUTE - len(self._requests[phone]))

    def _maybe_cleanup(self, now: float) -> None:
        """Periodically remove stale entries to prevent unbounded memory growth."""
        if now - self._last_cleanup < _CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        window_start = now - WINDOW_SECONDS
        stale_keys = [
            k for k, v in self._requests.items()
            if not v or all(t <= window_start for t in v)
        ]
        for k in stale_keys:
            del self._requests[k]


rate_limiter = RateLimiter()
