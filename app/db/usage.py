"""Usage statistics tracking and daily usage limits."""

from __future__ import annotations

import hashlib

from app.db.database import get_db
from app.utils.logger import get_logger

logger = get_logger("db.usage")

DAILY_USER_LIMIT = 30
DAILY_GLOBAL_LIMIT = 500
DAILY_VIDEO_USER_LIMIT = 5
DAILY_IMAGE_USER_LIMIT = 10


def _hash_phone(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()[:16]


async def check_daily_limit(user_phone: str, message_type: str = "text") -> tuple[bool, str]:
    """Check if user/global daily limits are exceeded.

    Returns (allowed, reason). If not allowed, reason explains why.
    """
    user_hash = _hash_phone(user_phone)
    try:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM daily_usage WHERE user_phone_hash = ? AND date = date('now')",
                (user_hash,),
            )
            user_total = (await cursor.fetchone())[0]
            if user_total >= DAILY_USER_LIMIT:
                return False, f"You've reached your daily limit of {DAILY_USER_LIMIT} checks. Try again tomorrow!"

            if message_type == "video":
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM daily_usage WHERE user_phone_hash = ? AND date = date('now') AND message_type = 'video'",
                    (user_hash,),
                )
                video_count = (await cursor.fetchone())[0]
                if video_count >= DAILY_VIDEO_USER_LIMIT:
                    return False, f"You've reached your daily limit of {DAILY_VIDEO_USER_LIMIT} video checks. Try sending the claim as text instead!"

            if message_type == "image":
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM daily_usage WHERE user_phone_hash = ? AND date = date('now') AND message_type = 'image'",
                    (user_hash,),
                )
                image_count = (await cursor.fetchone())[0]
                if image_count >= DAILY_IMAGE_USER_LIMIT:
                    return False, f"You've reached your daily limit of {DAILY_IMAGE_USER_LIMIT} image checks. Try sending the claim as text instead!"

            cursor = await db.execute(
                "SELECT COUNT(*) FROM daily_usage WHERE date = date('now')"
            )
            global_total = (await cursor.fetchone())[0]
            if global_total >= DAILY_GLOBAL_LIMIT:
                return False, "TruthBot is experiencing high demand today. Please try again tomorrow!"

            return True, ""
        finally:
            await db.close()
    except Exception:
        logger.exception("Failed to check daily limit")
        return True, ""


async def record_usage(user_phone: str, message_type: str) -> None:
    """Record a usage event for daily limit tracking."""
    user_hash = _hash_phone(user_phone)
    try:
        db = await get_db()
        try:
            await db.execute(
                "INSERT INTO daily_usage (user_phone_hash, message_type) VALUES (?, ?)",
                (user_hash, message_type),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        logger.exception("Failed to record usage")


async def log_usage(
    user_phone: str,
    message_type: str,
    verdict_label: str = "",
    confidence: float = 0.0,
    processing_ms: int = 0,
) -> None:
    """Log a usage event to the statistics database."""
    user_hash = _hash_phone(user_phone)
    try:
        db = await get_db()
        try:
            await db.execute(
                """INSERT INTO usage_stats (user_phone_hash, message_type, verdict_label, confidence, processing_ms)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_hash, message_type, verdict_label, confidence, processing_ms),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        logger.exception("Failed to log usage")


async def get_stats() -> dict:
    """Get basic usage statistics."""
    try:
        db = await get_db()
        try:
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
        finally:
            await db.close()
    except Exception:
        logger.exception("Failed to get stats")
        return {}
