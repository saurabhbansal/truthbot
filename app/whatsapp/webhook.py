from __future__ import annotations

import hashlib
import hmac
import time
from collections import OrderedDict

from fastapi import APIRouter, Query, Request, Response

from app.config import META_APP_SECRET, WHATSAPP_VERIFY_TOKEN
from app.router.content_router import route_message
from app.utils.logger import get_logger
from app.utils.rate_limiter import rate_limiter
from app.whatsapp.sender import send_text

logger = get_logger("webhook")

router = APIRouter()

_RATE_LIMIT_MSG = (
    "Whoa, slow down! You're sending messages faster than I can check them.\n\n"
    "Please wait a minute and try again."
)

_DEDUP_TTL = 120
_MAX_DEDUP_SIZE = 1000
_seen_messages: OrderedDict[str, float] = OrderedDict()


def _is_duplicate(message_id: str) -> bool:
    now = time.monotonic()
    while _seen_messages:
        oldest_id, oldest_time = next(iter(_seen_messages.items()))
        if now - oldest_time > _DEDUP_TTL:
            _seen_messages.pop(oldest_id)
        else:
            break
    if message_id in _seen_messages:
        return True
    _seen_messages[message_id] = now
    while len(_seen_messages) > _MAX_DEDUP_SIZE:
        _seen_messages.popitem(last=False)
    return False


def _verify_signature(payload: bytes, signature_header: str) -> bool:
    """Verify the X-Hub-Signature-256 HMAC from Meta."""
    if not META_APP_SECRET:
        return True
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        META_APP_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.get("")
async def verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
) -> Response:
    """Meta webhook verification handshake."""
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning("Webhook verification failed: token mismatch")
    return Response(content="Forbidden", status_code=403)


@router.post("")
async def receive(request: Request) -> dict:
    """Receive incoming WhatsApp messages."""
    raw_body = await request.body()

    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(raw_body, sig):
        logger.warning("Webhook signature verification failed")
        return {"status": "error", "message": "invalid signature"}

    body = await request.json()
    logger.debug("Incoming webhook payload: %s", body)

    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])

                for message in messages:
                    msg_id = message.get("id", "")
                    if msg_id and _is_duplicate(msg_id):
                        logger.debug("Skipping duplicate message: %s", msg_id)
                        continue

                    sender = message.get("from", "")
                    sender_name = ""
                    if contacts:
                        sender_name = contacts[0].get("profile", {}).get("name", "")

                    if not rate_limiter.is_allowed(sender):
                        logger.warning("Rate limited: %s", sender)
                        continue

                    logger.info(
                        "Message from %s (%s): type=%s",
                        sender_name,
                        sender,
                        message.get("type"),
                    )
                    await route_message(sender, sender_name, message)
    except Exception:
        logger.exception("Error processing webhook payload")

    return {"status": "ok"}
