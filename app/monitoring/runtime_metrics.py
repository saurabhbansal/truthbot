from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Mapping

_lock = asyncio.Lock()
_counters: Counter[str] = Counter()


def _key(
    name: str,
    *,
    content_type: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    category: str | None = None,
) -> str:
    parts = [name]
    if content_type:
        parts.append(f"content_type={content_type}")
    if provider:
        parts.append(f"provider={provider}")
    if model:
        parts.append(f"model={model}")
    if category:
        parts.append(f"category={category}")
    return "|".join(parts)


async def incr(
    name: str,
    *,
    content_type: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    category: str | None = None,
    value: int = 1,
) -> None:
    metric_key = _key(
        name,
        content_type=content_type,
        provider=provider,
        model=model,
        category=category,
    )
    async with _lock:
        _counters[metric_key] += value


async def snapshot() -> Mapping[str, int]:
    async with _lock:
        return dict(_counters)
