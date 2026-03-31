from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from app.utils.logger import get_logger

logger = get_logger("engines.retry")


def is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "resource_exhausted" in text


def is_transient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "service unavailable",
        "internal server error",
    )
    return any(marker in text for marker in markers)


def should_retry(exc: Exception) -> bool:
    return is_rate_limit_error(exc) or is_transient_error(exc)


async def with_retries(
    operation_name: str,
    func: Callable[[], Awaitable],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 0.6,
) -> object:
    """Run an async operation with bounded exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts or not should_retry(exc):
                raise
            sleep_for = base_delay_seconds * (2 ** (attempt - 1))
            sleep_for += random.uniform(0, 0.25)
            logger.warning(
                "%s failed (attempt %d/%d): %s; retrying in %.2fs",
                operation_name,
                attempt,
                attempts,
                type(exc).__name__,
                sleep_for,
            )
            await asyncio.sleep(sleep_for)
    assert last_exc is not None
    raise last_exc
