"""Hive Moderation API -- AI-generated content and deepfake detection for images and videos."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import HIVE_API_KEY
from app.utils.logger import get_logger

logger = get_logger("engines.hive")


@dataclass
class HiveDetectionResult:
    is_ai_generated: bool
    ai_confidence: float
    is_deepfake: bool
    deepfake_confidence: float
    model_detected: str
    raw_classes: dict


async def detect_ai_image(image_bytes: bytes) -> HiveDetectionResult:
    """Detect if an image is AI-generated using Hive Moderation API."""
    return await _detect_media(image_bytes, content_type="image/jpeg")


async def detect_ai_video(video_bytes: bytes) -> HiveDetectionResult:
    """Detect if a video is AI-generated / deepfake using Hive Moderation API."""
    return await _detect_media(video_bytes, content_type="video/mp4")


async def _detect_media(media_bytes: bytes, content_type: str) -> HiveDetectionResult:
    """Send media to Hive for AI-generation and deepfake detection."""
    if not HIVE_API_KEY:
        logger.warning("Hive API key not configured, skipping AI detection")
        return HiveDetectionResult(
            is_ai_generated=False,
            ai_confidence=0.0,
            is_deepfake=False,
            deepfake_confidence=0.0,
            model_detected="",
            raw_classes={},
        )

    headers = {
        "Authorization": f"Token {HIVE_API_KEY}",
        "Accept": "application/json",
    }

    ext = "jpg" if "image" in content_type else "mp4"
    files = {
        "media": (f"upload.{ext}", media_bytes, content_type),
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.thehive.ai/api/v2/task/sync",
                headers=headers,
                files=files,
            )
            data = resp.json()

        return _parse_hive_response(data)

    except Exception:
        logger.exception("Hive detection failed")
        return HiveDetectionResult(
            is_ai_generated=False,
            ai_confidence=0.0,
            is_deepfake=False,
            deepfake_confidence=0.0,
            model_detected="",
            raw_classes={},
        )


def _parse_hive_response(data: dict) -> HiveDetectionResult:
    """Parse Hive API response to extract AI-generation and deepfake signals."""
    is_ai = False
    ai_conf = 0.0
    is_deepfake = False
    deepfake_conf = 0.0
    model_detected = ""
    raw_classes: dict = {}

    try:
        status = data.get("status", [])
        if not status:
            return HiveDetectionResult(False, 0.0, False, 0.0, "", {})

        for output in status:
            response = output.get("response", {})
            for result_group in response.get("output", []):
                classes = result_group.get("classes", [])
                for cls in classes:
                    class_name = cls.get("class", "")
                    score = cls.get("score", 0.0)
                    raw_classes[class_name] = score

                    if class_name == "ai_generated" and score > 0.5:
                        is_ai = True
                        ai_conf = max(ai_conf, score)
                    elif class_name == "not_ai_generated" and score > 0.5:
                        ai_conf = max(ai_conf, 1.0 - score)
                    elif class_name == "deepfake" and score > 0.5:
                        is_deepfake = True
                        deepfake_conf = max(deepfake_conf, score)

                    if class_name.startswith("ai_model_") and score > 0.3:
                        model_detected = class_name.replace("ai_model_", "")

    except Exception:
        logger.exception("Error parsing Hive response")

    result = HiveDetectionResult(
        is_ai_generated=is_ai,
        ai_confidence=ai_conf,
        is_deepfake=is_deepfake,
        deepfake_confidence=deepfake_conf,
        model_detected=model_detected,
        raw_classes=raw_classes,
    )

    logger.info(
        "Hive result: ai=%s(%.2f) deepfake=%s(%.2f) model=%s",
        result.is_ai_generated,
        result.ai_confidence,
        result.is_deepfake,
        result.deepfake_confidence,
        result.model_detected,
    )
    return result
