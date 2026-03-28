from __future__ import annotations

import httpx

from app.config import WHATSAPP_ACCESS_TOKEN, WHATSAPP_MEDIA_URL, MAX_IMAGE_SIZE, MAX_VIDEO_SIZE
from app.utils.logger import get_logger

logger = get_logger("media")

_HEADERS = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}

_IMAGE_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"RIFF": "image/webp",
}


def _validate_media_bytes(data: bytes, expected_type: str = "image") -> bool:
    """Check magic bytes to verify the download is actual media, not an error page."""
    if len(data) < 8:
        return False
    if expected_type == "image":
        return any(data.startswith(magic) for magic in _IMAGE_MAGIC)
    if expected_type == "video":
        # MP4 files contain 'ftyp' within the first 12 bytes
        return b"ftyp" in data[:12] or data[:4] == b"\x1a\x45\xdf\xa3"  # webm
    return True


async def download_media(media_id: str, max_size: int | None = None) -> bytes | None:
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
            if url_resp.status_code != 200:
                logger.error("Media URL fetch failed: %s %s", url_resp.status_code, url_resp.text[:200])
                return None

            url_data = url_resp.json()
            media_url = url_data.get("url")
            if not media_url:
                logger.error("No URL in media response: %s", url_data)
                return None

            file_size = url_data.get("file_size", 0)
            if max_size and file_size and int(file_size) > max_size:
                logger.warning("Media %s too large: %d bytes (max %d)", media_id, int(file_size), max_size)
                return None

            media_resp = await client.get(media_url, headers=_HEADERS)
            if media_resp.status_code == 200:
                content = media_resp.content
                if max_size and len(content) > max_size:
                    logger.warning("Downloaded media %s exceeds size limit: %d bytes", media_id, len(content))
                    return None
                logger.info("Downloaded media %s (%d bytes)", media_id, len(content))
                return content

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
