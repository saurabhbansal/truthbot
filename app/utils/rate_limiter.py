"""Simple in-memory rate limiter per phone number."""

from __future__ import annotations

import time
from collections import defaultdict

MAX_REQUESTS_PER_MINUTE = 5
WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, phone: str) -> bool:
        """Check if a phone number is within rate limits."""
        now = time.time()
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
        recent = [t for t in self._requests[phone] if t > window_start]
        return max(0, MAX_REQUESTS_PER_MINUTE - len(recent))


rate_limiter = RateLimiter()
