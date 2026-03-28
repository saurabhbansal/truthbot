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
            {"id": f"fb_wrong_{verdict_id}", "title": "❌ Wrong"},
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
        await _log_feedback(verdict_id, user_hash, "positive")
        await send_text(to, "Thanks for the feedback! Glad I could help. 🙏")

    elif feedback_type == "no":
        await _log_feedback(verdict_id, user_hash, "negative")
        await send_list(
            to=to,
            body_text="Sorry about that! Can you tell me what went wrong?",
            button_text="Select reason",
            sections=[
                {
                    "title": "What went wrong?",
                    "rows": [
                        {"id": f"fbr_inaccurate_{verdict_id}", "title": "Verdict was inaccurate", "description": "The fact-check result was wrong"},
                        {"id": f"fbr_incomplete_{verdict_id}", "title": "Missing information", "description": "Important context was left out"},
                        {"id": f"fbr_sources_{verdict_id}", "title": "Bad sources", "description": "Sources were unreliable or irrelevant"},
                        {"id": f"fbr_unclear_{verdict_id}", "title": "Hard to understand", "description": "The explanation was confusing"},
                        {"id": f"fbr_other_{verdict_id}", "title": "Other", "description": "Something else went wrong"},
                    ],
                }
            ],
        )

    elif feedback_type == "wrong":
        await _log_feedback(verdict_id, user_hash, "wrong")
        await send_text(
            to,
            "Thanks for flagging this! If you have a source that shows the correct information, "
            "please share the link and I'll re-check.\n\n"
            "Just reply with the URL and I'll take another look. 🔍",
        )


async def handle_feedback_reason(to: str, list_id: str) -> None:
    """Handle a feedback reason selection from the list."""
    parts = list_id.split("_", 2)
    if len(parts) < 3:
        return

    reason = parts[1]
    verdict_id = parts[2]
    user_hash = _hash_phone(to)

    await _update_feedback_reason(verdict_id, user_hash, reason)

    responses = {
        "inaccurate": "Got it — I'll work on improving accuracy. If you have a correct source, share the link!",
        "incomplete": "Noted! I'll try to provide more complete context in the future.",
        "sources": "Thanks — I'll review my source selection for these types of claims.",
        "unclear": "I'll work on making my explanations clearer. Thanks for the feedback!",
        "other": "Thanks for letting me know. Your feedback helps me improve!",
    }

    await send_text(to, responses.get(reason, "Thanks for the feedback! 🙏"))


def generate_verdict_id() -> str:
    """Generate a unique verdict ID for feedback tracking."""
    return uuid.uuid4().hex[:12]


async def _log_feedback(
    verdict_id: str,
    user_hash: str,
    feedback_type: str,
    reason: str = "",
    source_link: str = "",
) -> None:
    """Log feedback to the database."""
    try:
        db = await get_db()
        await db.execute(
            """INSERT INTO feedback (verdict_id, user_phone_hash, feedback_type, negative_reason, source_link)
               VALUES (?, ?, ?, ?, ?)""",
            (verdict_id, user_hash, feedback_type, reason, source_link),
        )
        await db.commit()
        logger.info("Feedback logged: verdict=%s type=%s", verdict_id, feedback_type)
    except Exception:
        logger.exception("Failed to log feedback")


async def _update_feedback_reason(verdict_id: str, user_hash: str, reason: str) -> None:
    """Update the most recent feedback entry with the reason."""
    try:
        db = await get_db()
        await db.execute(
            """UPDATE feedback SET negative_reason = ?
               WHERE rowid = (
                   SELECT rowid FROM feedback
                   WHERE verdict_id = ? AND user_phone_hash = ?
                   ORDER BY created_at DESC LIMIT 1
               )""",
            (reason, verdict_id, user_hash),
        )
        await db.commit()
    except Exception:
        logger.exception("Failed to update feedback reason")


def _hash_phone(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()[:16]
