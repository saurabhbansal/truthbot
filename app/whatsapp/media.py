from __future__ import annotations

import httpx

from app.config import WHATSAPP_ACCESS_TOKEN, WHATSAPP_MEDIA_URL
from app.utils.logger import get_logger

logger = get_logger("media")

_HEADERS = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}


async def download_media(media_id: str) -> bytes | None:
    """Download media from WhatsApp by media ID.

    Two-step process:
    1. GET the media URL from the media ID
    2. GET the actual binary content from the media URL
    """
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            url_resp = await client.get(
                f"{WHATSAPP_MEDIA_URL}/{media_id}", headers=_HEADERS
            )
            url_data = url_resp.json()
            media_url = url_data.get("url")
            if not media_url:
                logger.error("No URL in media response: %s", url_data)
                return None

            media_resp = await client.get(media_url, headers=_HEADERS)
            if media_resp.status_code == 200:
                logger.info("Downloaded media %s (%d bytes)", media_id, len(media_resp.content))
                return media_resp.content

            logger.error("Media download failed: %s", media_resp.status_code)
            return None
    except Exception:
        logger.exception("Error downloading media %s", media_id)
        return None


async def get_media_url(media_id: str) -> str | None:
    """Get the download URL for a media ID without downloading."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{WHATSAPP_MEDIA_URL}/{media_id}", headers=_HEADERS
            )
            return resp.json().get("url")
    except Exception:
        logger.exception("Error getting media URL for %s", media_id)
        return None
