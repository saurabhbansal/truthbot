from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from app.config import WHATSAPP_VERIFY_TOKEN
from app.router.content_router import route_message
from app.utils.logger import get_logger
from app.utils.rate_limiter import rate_limiter
from app.whatsapp.sender import send_text

logger = get_logger("webhook")

router = APIRouter()

_RATE_LIMIT_MSG = (
    "Whoa, slow down! 😅 You're sending messages faster than I can check them.\n\n"
    "Please wait a minute and try again."
)


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
    body = await request.json()
    logger.debug("Incoming webhook payload: %s", body)

    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])

                for message in messages:
                    sender = message.get("from", "")
                    sender_name = ""
                    if contacts:
                        sender_name = contacts[0].get("profile", {}).get("name", "")

                    if not rate_limiter.is_allowed(sender):
                        logger.warning("Rate limited: %s", sender)
                        await send_text(sender, _RATE_LIMIT_MSG)
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
