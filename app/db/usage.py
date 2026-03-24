"""Usage statistics tracking."""

from __future__ import annotations

import hashlib

from app.db.database import get_db
from app.utils.logger import get_logger

logger = get_logger("db.usage")


async def log_usage(
    user_phone: str,
    message_type: str,
    verdict_label: str = "",
    confidence: float = 0.0,
    processing_ms: int = 0,
) -> None:
    """Log a usage event to the database."""
    user_hash = hashlib.sha256(user_phone.encode()).hexdigest()[:16]
    try:
        db = await get_db()
        await db.execute(
            """INSERT INTO usage_stats (user_phone_hash, message_type, verdict_label, confidence, processing_ms)
               VALUES (?, ?, ?, ?, ?)""",
            (user_hash, message_type, verdict_label, confidence, processing_ms),
        )
        await db.commit()
    except Exception:
        logger.exception("Failed to log usage")


async def get_stats() -> dict:
    """Get basic usage statistics."""
    try:
        db = await get_db()

        cursor = await db.execute("SELECT COUNT(*) FROM usage_stats")
        total = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(DISTINCT user_phone_hash) FROM usage_stats")
        unique_users = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT message_type, COUNT(*) FROM usage_stats GROUP BY message_type"
        )
        by_type = {row[0]: row[1] for row in await cursor.fetchall()}

        cursor = await db.execute(
            "SELECT verdict_label, COUNT(*) FROM usage_stats WHERE verdict_label != '' GROUP BY verdict_label"
        )
        by_verdict = {row[0]: row[1] for row in await cursor.fetchall()}

        return {
            "total_checks": total,
            "unique_users": unique_users,
            "by_type": by_type,
            "by_verdict": by_verdict,
        }
    except Exception:
        logger.exception("Failed to get stats")
        return {}
