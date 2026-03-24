"""Hash-based caching for fact-check results to avoid redundant API calls."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from app.db.database import get_db
from app.utils.logger import get_logger

logger = get_logger("db.cache")

CACHE_TTL_HOURS = 24


def content_hash(content: str) -> str:
    """Generate a deterministic hash for content deduplication."""
    normalized = content.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


async def get_cached_verdict(content: str) -> dict | None:
    """Check if we have a cached verdict for this content."""
    h = content_hash(content)
    try:
        db = await get_db()
        cursor = await db.execute(
            "SELECT verdict_json, created_at FROM cache WHERE content_hash = ?",
            (h,),
        )
        row = await cursor.fetchone()

        if not row:
            return None

        created_at = datetime.fromisoformat(row[1])
        if datetime.utcnow() - created_at > timedelta(hours=CACHE_TTL_HOURS):
            await db.execute("DELETE FROM cache WHERE content_hash = ?", (h,))
            await db.commit()
            logger.info("Cache expired for hash %s", h[:12])
            return None

        logger.info("Cache hit for hash %s", h[:12])
        return json.loads(row[0])

    except Exception:
        logger.exception("Cache lookup failed")
        return None


async def set_cached_verdict(content: str, verdict_data: dict) -> None:
    """Store a verdict in the cache."""
    h = content_hash(content)
    try:
        db = await get_db()
        await db.execute(
            "INSERT OR REPLACE INTO cache (content_hash, verdict_json) VALUES (?, ?)",
            (h, json.dumps(verdict_data)),
        )
        await db.commit()
        logger.info("Cached verdict for hash %s", h[:12])
    except Exception:
        logger.exception("Cache write failed")
