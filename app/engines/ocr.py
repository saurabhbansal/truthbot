"""OCR engine -- extract text from images using Google Cloud Vision API."""

from __future__ import annotations

import base64

import httpx

from app.config import GOOGLE_API_KEY
from app.utils.logger import get_logger

logger = get_logger("engines.ocr")

VISION_API_URL = "https://vision.googleapis.com/v1/images:annotate"


async def extract_text_from_image(image_bytes: bytes) -> str:
    """Extract text from an image using Google Cloud Vision OCR.

    Uses DOCUMENT_TEXT_DETECTION for better accuracy on screenshots,
    documents, and dense text images.
    """
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "requests": [
            {
                "image": {"content": b64_image},
                "features": [
                    {"type": "DOCUMENT_TEXT_DETECTION", "maxResults": 1},
                ],
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                VISION_API_URL,
                params={"key": GOOGLE_API_KEY},
                json=payload,
            )

        if resp.status_code != 200:
            logger.error("Vision API error %d: %s", resp.status_code, resp.text[:300])
            return ""

        data = resp.json()

        if "error" in data:
            logger.error("Vision API returned error: %s", data["error"])
            return ""

        responses = data.get("responses", [])
        if not responses:
            return ""

        first = responses[0]
        if "error" in first:
            logger.error("Vision API response error: %s", first["error"])
            return ""

        full_text = first.get("fullTextAnnotation", {}).get("text", "")
        if not full_text:
            annotations = first.get("textAnnotations", [])
            if annotations:
                full_text = annotations[0].get("description", "")

        full_text = full_text.strip()
        if full_text:
            logger.info("OCR: extracted %d chars from image", len(full_text))
        else:
            logger.info("OCR: no text found in image")
        return full_text

    except Exception:
        logger.exception("OCR failed")
        return ""


async def extract_labels_from_image(image_bytes: bytes) -> list[str]:
    """Extract labels/objects from an image for context."""
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "requests": [
            {
                "image": {"content": b64_image},
                "features": [
                    {"type": "LABEL_DETECTION", "maxResults": 10},
                ],
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                VISION_API_URL,
                params={"key": GOOGLE_API_KEY},
                json=payload,
            )

        if resp.status_code != 200:
            logger.error("Vision label API error %d: %s", resp.status_code, resp.text[:300])
            return []

        data = resp.json()

        responses = data.get("responses", [])
        if not responses:
            return []

        labels = [
            ann.get("description", "")
            for ann in responses[0].get("labelAnnotations", [])
        ]
        logger.info("Vision labels: %s", labels)
        return labels

    except Exception:
        logger.exception("Label detection failed")
        return []
