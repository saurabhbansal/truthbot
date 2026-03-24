from __future__ import annotations

import re
from typing import Any

from app.utils.logger import get_logger
from app.whatsapp.sender import send_text

logger = get_logger("router")

_URL_PATTERN = re.compile(r"https?://[^\s]+")

# Messages that trigger the help/onboarding flow
_GREETING_WORDS = {"hi", "hello", "hey", "hola", "namaste", "start"}
_HELP_WORDS = {"help", "menu", "commands", "?"}

_ONBOARDING_MSG = (
    "Hey there! I'm TruthBot 🔍\n\n"
    "I help you check if messages, images, links, and videos are real or fake.\n\n"
    "*HOW TO USE ME:*\n"
    "Just forward me anything you want checked! That's it.\n\n"
    "I can check:\n"
    "• Text messages & chain forwards\n"
    "• News links & articles\n"
    "• Images & screenshots\n"
    "• Videos (AI-generated & deepfakes)\n\n"
    "Try it now — forward me something from your groups!\n\n"
    'Type "help" anytime for tips.'
)

_HELP_MSG = (
    "Here's how I can help:\n\n"
    "*FORWARD* me any:\n"
    "• Text message or chain forward\n"
    "• Image or screenshot\n"
    "• News link or article URL\n"
    "• Video clip\n\n"
    "And I'll tell you if it's real, fake, or misleading.\n\n"
    "*TIPS:*\n"
    "• The more context, the better — forward the full message\n"
    "• I work best with specific claims\n"
    "• I'll always tell you when I'm not sure\n\n"
    "*COMING SOON:*\n"
    "• Audio/voice note checking\n"
    "• Hindi responses\n"
    "• Group chat support (@TruthBot)"
)

_UNSUPPORTED_MSG = (
    "Hey! I got your {type}, but I can't fact-check those yet.\n\n"
    "Forward me a text message, image, video, or link and I'll get to work!"
)

_AUDIO_MSG = (
    "Hey! I got your voice note, but I can't check audio messages yet (coming soon!).\n\n"
    "In the meantime, could you type out the main claim you want me to check? "
    "Or forward the original text/image instead?"
)

_REDIRECT_MSG = (
    "Hey! I'm just a fact-checker, so I'm best at checking if something is true or fake.\n\n"
    "If you have a suspicious message, image, video, or link — "
    "just forward it to me and I'll investigate!\n\n"
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

    # Fact-check the text claim
    await send_text(sender, "Got it! Checking this now... ⏳\n(usually takes 5-10 seconds)")

    # TODO Phase 3: Replace with actual text fact-check engine
    await send_text(
        sender,
        f"[DEBUG] Received text claim to fact-check:\n\n\"{text_body}\"\n\n"
        "Fact-check engine coming in Phase 3!",
    )


async def _handle_image(sender: str, sender_name: str, message: dict) -> None:
    image_data = message.get("image", {})
    caption = image_data.get("caption", "")
    media_id = image_data.get("id", "")

    await send_text(sender, "Got your image! Analyzing it... 🔍\n(this may take 10-15 seconds)")

    # TODO Phase 4: Replace with actual image analysis engine
    await send_text(
        sender,
        f"[DEBUG] Received image to analyze:\n"
        f"Media ID: {media_id}\n"
        f"Caption: {caption or '(none)'}\n\n"
        "Image analysis engine coming in Phase 4!",
    )


async def _handle_video(sender: str, sender_name: str, message: dict) -> None:
    video_data = message.get("video", {})
    caption = video_data.get("caption", "")
    media_id = video_data.get("id", "")

    await send_text(
        sender,
        "Got your video! This takes a bit longer to analyze — "
        "I'll get back to you in about 30-60 seconds. Hang tight! ⏳",
    )

    # TODO Phase 4b: Replace with actual video analysis engine
    await send_text(
        sender,
        f"[DEBUG] Received video to analyze:\n"
        f"Media ID: {media_id}\n"
        f"Caption: {caption or '(none)'}\n\n"
        "Video analysis engine coming in Phase 4b!",
    )


async def _handle_link(sender: str, sender_name: str, text: str) -> None:
    urls = _URL_PATTERN.findall(text)
    await send_text(sender, "Got the link! Let me check the article and the source... 🔍")

    # TODO Phase 5: Replace with actual link analysis engine
    await send_text(
        sender,
        f"[DEBUG] Received link to fact-check:\n"
        f"URL(s): {', '.join(urls)}\n\n"
        "Link analysis engine coming in Phase 5!",
    )


async def _handle_interactive(sender: str, sender_name: str, message: dict) -> None:
    """Handle button/list replies (used for feedback)."""
    interactive = message.get("interactive", {})
    reply_type = interactive.get("type", "")

    if reply_type == "button_reply":
        button_id = interactive.get("button_reply", {}).get("id", "")
        await _handle_feedback_button(sender, button_id)
    elif reply_type == "list_reply":
        list_id = interactive.get("list_reply", {}).get("id", "")
        await _handle_feedback_list(sender, list_id)


async def _handle_feedback_button(sender: str, button_id: str) -> None:
    """Handle feedback button presses."""
    if button_id == "feedback_helpful":
        await send_text(sender, "Glad I could help! Forward me anything else you want checked. 👍")
    elif button_id == "feedback_wrong":
        from app.whatsapp.sender import send_list

        await send_list(
            sender,
            "Thanks for letting me know! What was wrong?",
            "Select reason",
            [
                {
                    "title": "Feedback",
                    "rows": [
                        {"id": "fb_incorrect", "title": "Verdict is incorrect"},
                        {"id": "fb_context", "title": "Missing important context"},
                        {"id": "fb_sources", "title": "Sources seem unreliable"},
                        {"id": "fb_other", "title": "Other"},
                    ],
                }
            ],
        )


async def _handle_feedback_list(sender: str, list_id: str) -> None:
    """Handle feedback list selection."""
    if list_id == "fb_incorrect":
        await send_text(
            sender,
            "Got it. If you have a link to a reliable source that shows the correct info, "
            "send it and I'll take another look!\n\n"
            "Otherwise, I've noted your feedback. Thanks for helping me improve! 🙏",
        )
    elif list_id == "fb_context":
        await send_text(
            sender,
            "Thanks! I'll try to include more context next time. "
            "If you can share what I missed, that would help a lot!",
        )
    elif list_id == "fb_sources":
        await send_text(
            sender,
            "I appreciate that — I'll double-check my sources. "
            "If you have a more reliable source, feel free to send it!",
        )
    elif list_id == "fb_other":
        await send_text(
            sender,
            "Thanks for the feedback! Tell me more about what was wrong "
            "and I'll use it to improve.",
        )
