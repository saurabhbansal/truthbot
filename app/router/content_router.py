"""Content router -- dispatches incoming messages to the appropriate engine."""

from __future__ import annotations

import re
from typing import Any

from app.engines.image_handler import fact_check_image
from app.engines.link_handler import extract_urls, fact_check_link
from app.engines.text_handler import fact_check_text
from app.engines.video_handler import fact_check_video
from app.feedback.feedback_handler import (
    generate_verdict_id,
    handle_feedback_reason,
    handle_feedback_response,
    send_feedback_buttons,
)
from app.config import MAX_IMAGE_SIZE, MAX_VIDEO_SIZE
from app.db.usage import check_daily_limit, record_usage
from app.utils.logger import get_logger
from app.whatsapp.media import download_media
from app.whatsapp.sender import send_text

logger = get_logger("router")

_URL_PATTERN = re.compile(r"https?://[^\s]+")

_GREETING_WORDS = {"hi", "hello", "hey", "hola", "namaste", "start"}
_HELP_WORDS = {"help", "menu", "commands", "?"}

_ONBOARDING_MSG = (
    "Hey there! I'm TruthBot 🔍\n\n"
    "I help you check if messages, images, links, and videos are real or fake.\n\n"
    "*HOW TO USE ME:*\n"
    "Forward or send me anything you want checked! That's it.\n\n"
    "I can check:\n"
    "• Text messages & chain forwards\n"
    "• News links & articles\n"
    "• Images & screenshots (forwarded or from your gallery)\n"
    "• Videos (AI-generated & deepfakes)\n\n"
    "Try it now — send me something suspicious!\n\n"
    'Type "help" anytime for tips.'
)

_HELP_MSG = (
    "Here's how I can help:\n\n"
    "*SEND or FORWARD* me any:\n"
    "• Text message or chain forward\n"
    "• Image or screenshot (from gallery or camera too!)\n"
    "• News link or article URL\n"
    "• Video clip\n\n"
    "And I'll tell you if it's real, fake, or misleading.\n\n"
    "*TIPS:*\n"
    "• The more context, the better — send the full message\n"
    "• I work best with specific claims\n"
    "• I'll always tell you when I'm not sure\n\n"
    "*COMING SOON:*\n"
    "• Audio/voice note checking\n"
    "• Hindi responses\n"
    "• Group chat support (@TruthBot)"
)

_UNSUPPORTED_MSG = (
    "Hey! I got your {type}, but I can't fact-check those yet.\n\n"
    "Send or forward me a text message, image, video, or link and I'll get to work!"
)

_AUDIO_MSG = (
    "Hey! I got your voice note, but I can't check audio messages yet (coming soon!).\n\n"
    "In the meantime, could you type out the main claim you want me to check? "
    "Or forward the original text/image instead?"
)

_REDIRECT_MSG = (
    "Hey! I'm just a fact-checker, so I'm best at checking if something is true or fake.\n\n"
    "If you have a suspicious message, image, video, or link — "
    "just send or forward it to me and I'll investigate!\n\n"
    'Type "help" if you need tips.'
)


async def route_message(sender: str, sender_name: str, message: dict[str, Any]) -> None:
    """Route an incoming message to the appropriate handler."""
    msg_type = message.get("type", "")
    logger.info("Routing message type=%s from %s", msg_type, sender)

    if msg_type == "text":
        await _handle_text(sender, sender_name, message)
    elif msg_type == "image":
        await _handle_image(sender, sender_name, message)
    elif msg_type == "video":
        await _handle_video(sender, sender_name, message)
    elif msg_type in ("audio", "voice"):
        await send_text(sender, _AUDIO_MSG)
    elif msg_type == "document":
        await send_text(sender, _UNSUPPORTED_MSG.format(type="document"))
    elif msg_type == "interactive":
        await _handle_interactive(sender, sender_name, message)
    elif msg_type in ("sticker", "contacts", "location"):
        await send_text(sender, _UNSUPPORTED_MSG.format(type=msg_type))
    else:
        await send_text(sender, _REDIRECT_MSG)


async def _handle_text(sender: str, sender_name: str, message: dict) -> None:
    text_body: str = message.get("text", {}).get("body", "").strip()
    text_lower = text_body.lower().strip()

    if text_lower in _GREETING_WORDS:
        await send_text(sender, _ONBOARDING_MSG)
        return

    if text_lower in _HELP_WORDS:
        await send_text(sender, _HELP_MSG)
        return

    if _URL_PATTERN.search(text_body):
        await _handle_link(sender, sender_name, text_body)
        return

    allowed, reason = await check_daily_limit(sender, "text")
    if not allowed:
        await send_text(sender, reason)
        return

    await record_usage(sender, "text")
    await send_text(sender, "Got it! Checking this now... ⏳\n(usually takes 5-10 seconds)")

    try:
        result_message, verdicts = await fact_check_text(text_body)
        await send_text(sender, result_message)
    except Exception:
        logger.exception("Text fact-check failed")
        await send_text(
            sender,
            "Oops, something went wrong while checking this. Please try again in a moment!",
        )
        return

    try:
        if verdicts:
            verdict_id = generate_verdict_id()
            await send_feedback_buttons(sender, verdict_id)
    except Exception:
        logger.exception("Failed to send feedback buttons for text")


async def _handle_image(sender: str, sender_name: str, message: dict) -> None:
    image_data = message.get("image", {})
    caption = image_data.get("caption", "")
    media_id = image_data.get("id", "")

    allowed, reason = await check_daily_limit(sender, "image")
    if not allowed:
        await send_text(sender, reason)
        return

    await record_usage(sender, "image")
    await send_text(sender, "Got your image! Analyzing it... 🔍\n(this may take 10-15 seconds)")

    try:
        image_bytes = await download_media(media_id, max_size=MAX_IMAGE_SIZE, expected_type="image")
        if not image_bytes:
            await send_text(sender, "Sorry, I couldn't download the image. It may be too large (max 10MB) or unavailable. Try sending it again?")
            return

        result = await fact_check_image(image_bytes, caption=caption)
        await send_text(sender, result)
    except Exception:
        logger.exception("Image fact-check failed")
        await send_text(
            sender,
            "Oops, something went wrong analyzing this image. Please try again!",
        )
        return

    try:
        verdict_id = generate_verdict_id()
        await send_feedback_buttons(sender, verdict_id)
    except Exception:
        logger.exception("Failed to send feedback buttons for image")


async def _handle_video(sender: str, sender_name: str, message: dict) -> None:
    video_data = message.get("video", {})
    caption = video_data.get("caption", "")
    media_id = video_data.get("id", "")

    allowed, reason = await check_daily_limit(sender, "video")
    if not allowed:
        await send_text(sender, reason)
        return

    await record_usage(sender, "video")
    await send_text(
        sender,
        "Got your video! This takes a bit longer to analyze — "
        "I'll get back to you in about 30-60 seconds. Hang tight! ⏳",
    )

    try:
        video_bytes = await download_media(media_id, max_size=MAX_VIDEO_SIZE, expected_type="video")
        if not video_bytes:
            await send_text(sender, "Sorry, I couldn't download the video. It may be too large (max 16MB) or unavailable. Try sending it again?")
            return

        result = await fact_check_video(video_bytes, caption=caption)
        await send_text(sender, result)
    except Exception:
        logger.exception("Video fact-check failed")
        await send_text(
            sender,
            "Oops, something went wrong analyzing this video. Please try again!",
        )
        return

    try:
        verdict_id = generate_verdict_id()
        await send_feedback_buttons(sender, verdict_id)
    except Exception:
        logger.exception("Failed to send feedback buttons for video")


async def _handle_link(sender: str, sender_name: str, text: str) -> None:
    urls = extract_urls(text)
    if not urls:
        await send_text(sender, _REDIRECT_MSG)
        return

    allowed, reason = await check_daily_limit(sender, "link")
    if not allowed:
        await send_text(sender, reason)
        return

    await record_usage(sender, "link")
    await send_text(sender, "Got the link! Let me check the article and the source... 🔍")

    try:
        result = await fact_check_link(urls[0])
        await send_text(sender, result)
    except Exception:
        logger.exception("Link fact-check failed")
        await send_text(
            sender,
            "Oops, something went wrong checking this link. Please try again!",
        )
        return

    try:
        verdict_id = generate_verdict_id()
        await send_feedback_buttons(sender, verdict_id)
    except Exception:
        logger.exception("Failed to send feedback buttons for link")


async def _handle_interactive(sender: str, sender_name: str, message: dict) -> None:
    """Handle button/list replies (feedback mechanism)."""
    interactive = message.get("interactive", {})
    reply_type = interactive.get("type", "")

    if reply_type == "button_reply":
        button_id = interactive.get("button_reply", {}).get("id", "")
        if button_id.startswith("fb_"):
            await handle_feedback_response(sender, button_id)
    elif reply_type == "list_reply":
        list_id = interactive.get("list_reply", {}).get("id", "")
        if list_id.startswith("fbr_"):
            await handle_feedback_reason(sender, list_id)
