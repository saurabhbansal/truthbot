"""Feedback mechanism -- interactive buttons, follow-up questions, logging."""

from __future__ import annotations

import hashlib
import uuid

from app.db.database import get_db
from app.whatsapp.sender import send_buttons, send_text, send_list
from app.utils.logger import get_logger

logger = get_logger("feedback")


async def send_feedback_buttons(to: str, verdict_id: str) -> None:
    """Send feedback buttons after a verdict."""
    await send_buttons(
        to=to,
        body_text="Was this helpful? Your feedback helps me improve!",
        buttons=[
            {"id": f"fb_yes_{verdict_id}", "title": "👍 Helpful"},
            {"id": f"fb_no_{verdict_id}", "title": "👎 Not Helpful"},
        ],
    )


async def handle_feedback_response(to: str, button_id: str) -> None:
    """Handle a feedback button press."""
    parts = button_id.split("_", 2)
    if len(parts) < 3:
        return

    feedback_type = parts[1]
    verdict_id = parts[2]
    user_hash = _hash_phone(to)

    if feedback_type == "yes":
        await _upsert_feedback(verdict_id, user_hash, "positive")
        await send_text(to, "Thanks for the feedback! Glad I could help. 🙏")

    elif feedback_type == "no":
        await _upsert_feedback(verdict_id, user_hash, "negative")
        await send_list(
            to=to,
            body_text="Sorry about that! Can you tell me what went wrong?",
            button_text="Select reason",
            sections=[
                {
                    "title": "What went wrong?",
                    "rows": [
                        {"id": f"fbr_wrongverdict_{verdict_id}", "title": "Wrong verdict", "description": "The fact-check result was wrong"},
                        {"id": f"fbr_incomplete_{verdict_id}", "title": "Missing information", "description": "Important context was left out"},
                        {"id": f"fbr_sources_{verdict_id}", "title": "Bad sources", "description": "Sources were unreliable or irrelevant"},
                        {"id": f"fbr_unclear_{verdict_id}", "title": "Hard to understand", "description": "The explanation was confusing"},
                        {"id": f"fbr_other_{verdict_id}", "title": "Other", "description": "Something else went wrong"},
                    ],
                }
            ],
        )

async def handle_feedback_reason(to: str, list_id: str) -> None:
    """Handle a feedback reason selection from the list."""
    parts = list_id.split("_", 2)
    if len(parts) < 3:
        return

    reason = parts[1]
    verdict_id = parts[2]
    user_hash = _hash_phone(to)

    await _upsert_feedback(verdict_id, user_hash, "negative", reason=reason)

    responses = {
        "wrongverdict": (
            "Thanks for flagging this. If you have a source that shows the correct information, "
            "please share the link and I'll re-check."
        ),
        "incomplete": "Noted! I'll try to provide more complete context in the future.",
        "sources": "Thanks — I'll review my source selection for these types of claims.",
        "unclear": "I'll work on making my explanations clearer. Thanks for the feedback!",
        "other": "Thanks for letting me know. Your feedback helps me improve!",
    }

    await send_text(to, responses.get(reason, "Thanks for the feedback! 🙏"))


def generate_verdict_id() -> str:
    """Generate a unique verdict ID for feedback tracking."""
    return uuid.uuid4().hex[:12]


async def _upsert_feedback(
    verdict_id: str,
    user_hash: str,
    feedback_type: str,
    reason: str = "",
    source_link: str = "",
) -> None:
    """Upsert latest feedback for verdict/user so users can revise feedback."""
    try:
        db = await get_db()
        try:
            cursor = await db.execute(
                """UPDATE feedback
                   SET feedback_type = ?, negative_reason = ?, source_link = ?, created_at = CURRENT_TIMESTAMP
                   WHERE rowid = (
                       SELECT rowid FROM feedback
                       WHERE verdict_id = ? AND user_phone_hash = ?
                       ORDER BY created_at DESC LIMIT 1
                   )""",
                (feedback_type, reason, source_link, verdict_id, user_hash),
            )
            if cursor.rowcount == 0:
                await db.execute(
                    """INSERT INTO feedback (verdict_id, user_phone_hash, feedback_type, negative_reason, source_link)
                       VALUES (?, ?, ?, ?, ?)""",
                    (verdict_id, user_hash, feedback_type, reason, source_link),
                )
            await db.commit()
        finally:
            await db.close()
        logger.info("Feedback upserted: verdict=%s type=%s", verdict_id, feedback_type)
    except Exception:
        logger.exception("Failed to upsert feedback")


async def get_feedback_stats(days: int = 30) -> dict:
    """Aggregate feedback stats for dashboard and monitoring."""
    try:
        db = await get_db()
        try:
            cursor = await db.execute(
                """SELECT feedback_type, COUNT(*)
                   FROM feedback
                   WHERE created_at >= datetime('now', ?)
                   GROUP BY feedback_type""",
                (f"-{days} days",),
            )
            by_type = {row[0]: row[1] for row in await cursor.fetchall()}

            cursor = await db.execute(
                """SELECT negative_reason, COUNT(*)
                   FROM feedback
                   WHERE created_at >= datetime('now', ?)
                     AND feedback_type = 'negative'
                     AND COALESCE(negative_reason, '') != ''
                   GROUP BY negative_reason
                   ORDER BY COUNT(*) DESC""",
                (f"-{days} days",),
            )
            negative_reasons = {row[0]: row[1] for row in await cursor.fetchall()}

            cursor = await db.execute(
                """SELECT date(created_at), COUNT(*)
                   FROM feedback
                   WHERE created_at >= datetime('now', ?)
                   GROUP BY date(created_at)
                   ORDER BY date(created_at)""",
                (f"-{days} days",),
            )
            trend = [{"date": row[0], "count": row[1]} for row in await cursor.fetchall()]

            total = sum(by_type.values())
            positive = by_type.get("positive", 0)
            negative = by_type.get("negative", 0)
            positive_rate = round((positive / total) * 100, 2) if total else 0.0

            return {
                "window_days": days,
                "total_feedback": total,
                "positive": positive,
                "negative": negative,
                "positive_rate_pct": positive_rate,
                "by_type": by_type,
                "negative_reasons": negative_reasons,
                "trend": trend,
            }
        finally:
            await db.close()
    except Exception:
        logger.exception("Failed to get feedback stats")
        return {
            "window_days": days,
            "total_feedback": 0,
            "positive": 0,
            "negative": 0,
            "positive_rate_pct": 0.0,
            "by_type": {},
            "negative_reasons": {},
            "trend": [],
        }


async def get_feedback_flagged_claim_hashes(min_wrong: int = 2, days: int = 30) -> list[str]:
    """Return claim hashes repeatedly marked as wrong verdict."""
    try:
        db = await get_db()
        try:
            cursor = await db.execute(
                """SELECT vc.content_hash
                   FROM feedback f
                   JOIN verdict_context vc ON vc.verdict_id = f.verdict_id
                   WHERE f.created_at >= datetime('now', ?)
                     AND f.feedback_type = 'negative'
                     AND f.negative_reason = 'wrongverdict'
                     AND vc.content_hash IS NOT NULL
                     AND vc.content_hash != ''
                   GROUP BY vc.content_hash
                   HAVING COUNT(*) >= ?""",
                (f"-{days} days", min_wrong),
            )
            return [row[0] for row in await cursor.fetchall()]
        finally:
            await db.close()
    except Exception:
        logger.exception("Failed to fetch flagged claim hashes")
        return []


async def register_verdict_context(verdict_id: str, content_hash: str, message_type: str) -> None:
    """Store verdict context for feedback learning loops."""
    try:
        db = await get_db()
        try:
            await db.execute(
                """INSERT OR REPLACE INTO verdict_context (verdict_id, content_hash, message_type)
                   VALUES (?, ?, ?)""",
                (verdict_id, content_hash, message_type),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        logger.exception("Failed to register verdict context")


async def _log_feedback(
    verdict_id: str,
    user_hash: str,
    feedback_type: str,
    reason: str = "",
    source_link: str = "",
) -> None:
    """Backward-compatible alias for older call sites."""
    await _upsert_feedback(verdict_id, user_hash, feedback_type, reason, source_link)


async def _update_feedback_reason(verdict_id: str, user_hash: str, reason: str) -> None:
    """Backward-compatible alias for older call sites."""
    await _upsert_feedback(verdict_id, user_hash, "negative", reason=reason)


def _hash_phone(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()[:16]
