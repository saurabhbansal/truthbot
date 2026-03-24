from __future__ import annotations

from typing import Any

import httpx

from app.config import WHATSAPP_ACCESS_TOKEN, WHATSAPP_API_URL
from app.utils.logger import get_logger

logger = get_logger("sender")

_HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}


async def send_text(to: str, text: str) -> dict:
    """Send a plain text message."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    return await _post(payload)


async def send_buttons(to: str, body_text: str, buttons: list[dict[str, str]]) -> dict:
    """Send an interactive message with up to 3 buttons.

    Each button dict: {"id": "btn_id", "title": "Button Label"}
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": btn} for btn in buttons[:3]
                ]
            },
        },
    }
    return await _post(payload)


async def send_list(
    to: str,
    body_text: str,
    button_text: str,
    sections: list[dict[str, Any]],
) -> dict:
    """Send an interactive list message.

    sections example:
    [{"title": "Options", "rows": [{"id": "opt1", "title": "Option 1"}]}]
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body_text},
            "action": {"button": button_text, "sections": sections},
        },
    }
    return await _post(payload)


async def _post(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(WHATSAPP_API_URL, headers=_HEADERS, json=payload)
        data = resp.json()
        if resp.status_code != 200:
            logger.error("WhatsApp API error %s: %s", resp.status_code, data)
        return data
