"""Image fact-check handler -- OpenAI vision primary with targeted escalation."""

from __future__ import annotations

import asyncio
import base64

from google.genai import types
from openai import AsyncOpenAI

from app.config import GEMINI_PRO_MODEL, OPENAI_API_KEY
from app.engines.gemini_client import client as gemini_client
from app.engines.retry_utils import is_rate_limit_error, with_retries
from app.engines.ocr import extract_text_from_image
from app.engines.text_handler import fact_check_text
from app.monitoring.runtime_metrics import incr
from app.utils.logger import get_logger

logger = get_logger("engines.image")

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

_VISION_PROMPT = (
    "Analyze this image carefully. Provide:\n\n"
    "1. **Description**: What does the image show? Describe people, objects, text overlays, "
    "logos, screenshots, or any visual content.\n"
    "2. **Text transcription**: If there is ANY text visible in the image (headlines, captions, "
    "watermarks, screenshots of messages, social media posts), transcribe it exactly.\n"
    "3. **Claims**: If the image makes or implies any factual claims (through text, context, "
    "or visual content), list each claim clearly.\n"
    "4. **AI assessment**: Does this image appear to be AI-generated, digitally manipulated, "
    "or a deepfake? Note any visual artifacts, inconsistencies, or signs of manipulation.\n\n"
    "Be thorough and factual. Do not speculate beyond what is visible."
)


def _detect_image_mime(image_bytes: bytes) -> str:
    if image_bytes[:2] == b'\xff\xd8':
        return "image/jpeg"
    if image_bytes[:4] == b'\x89PNG':
        return "image/png"
    if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"


async def _analyze_image_with_gemini(image_bytes: bytes) -> str:
    """Analyze image with Gemini first to reduce OpenAI cost."""
    mime = _detect_image_mime(image_bytes)
    try:
        response = await with_retries(
            "image.gemini",
            lambda: asyncio.to_thread(
                gemini_client.models.generate_content,
                model=GEMINI_PRO_MODEL,
                contents=[
                    _VISION_PROMPT,
                    types.Part.from_bytes(data=image_bytes, mime_type=mime),
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=1500,
                ),
            ),
        )
        content = response.text or ""
        logger.info("Gemini image analysis: %d chars", len(content))
        await incr("vision_success", content_type="image", provider="gemini", model=GEMINI_PRO_MODEL)
        return content.strip()
    except Exception as exc:
        if is_rate_limit_error(exc):
            logger.warning("Gemini image analysis rate-limited")
            await incr(
                "vision_failure",
                content_type="image",
                provider="gemini",
                model=GEMINI_PRO_MODEL,
                category="quota",
            )
        else:
            logger.exception("Gemini image analysis failed")
            await incr(
                "vision_failure",
                content_type="image",
                provider="gemini",
                model=GEMINI_PRO_MODEL,
                category="runtime",
            )
        return ""


async def _analyze_image_with_openai(image_bytes: bytes, model: str) -> str:
    """Analyze image with OpenAI as fallback/escalation."""
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    try:
        response = await with_retries(
            f"image.openai.{model}",
            lambda: _client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{_detect_image_mime(image_bytes)};base64,{b64_image}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=1500,
                temperature=0.1,
            ),
        )

        content = response.choices[0].message.content or ""
        logger.info("OpenAI image analysis (%s): %d chars", model, len(content))
        await incr("vision_success", content_type="image", provider="openai", model=model)
        return content.strip()

    except Exception:
        logger.exception("OpenAI image analysis failed for model=%s", model)
        await incr(
            "vision_failure",
            content_type="image",
            provider="openai",
            model=model,
            category="runtime",
        )
        return ""


async def fact_check_image(image_bytes: bytes, caption: str = "") -> str:
    """Full image fact-checking pipeline.

    1. Run Gemini image analysis + OCR in parallel
    2. Check for AI-generated/manipulated content from vision analysis
    3. Combine vision description + OCR text + caption for fact-checking
    """
    ocr_task = extract_text_from_image(image_bytes)
    vision_analysis, ocr_text = await asyncio.gather(
        _analyze_image_with_openai(image_bytes, model="gpt-4o"),
        ocr_task,
    )
    if _needs_escalation(vision_analysis):
        logger.info("Image analysis escalation triggered -> gpt-5.4")
        escalated = await _analyze_image_with_openai(image_bytes, model="gpt-5.4")
        if escalated:
            vision_analysis = escalated
    if not vision_analysis:
        # Last resort if OpenAI path is unavailable.
        vision_analysis = await _analyze_image_with_gemini(image_bytes)

    parts: list[str] = []

    # Check for AI-generated content from vision analysis
    ai_keywords = ("ai-generated", "ai generated", "artificially generated",
                   "digitally manipulated", "deepfake", "appears to be generated")
    vision_lower = vision_analysis.lower()
    if any(kw in vision_lower for kw in ai_keywords):
        if any(w in vision_lower for w in ("likely ai", "appears to be ai", "appears to be generated",
                                            "is ai-generated", "is ai generated")):
            parts.append("🤖 *POSSIBLE AI-GENERATED IMAGE*")
            parts.append("")
            parts.append(
                "This image shows signs of being AI-generated or digitally manipulated. "
                "Always verify the source before sharing."
            )
            parts.append("")

    # Build the text to fact-check from all available sources
    fact_check_input = ""

    if caption:
        fact_check_input = caption

    if ocr_text:
        fact_check_input = f"{fact_check_input}\n{ocr_text}".strip() if fact_check_input else ocr_text

    # Vision analysis often extracts text that OCR misses (stylized fonts, memes, etc.)
    if vision_analysis:
        fact_check_input = f"{fact_check_input}\n\nImage analysis: {vision_analysis}".strip()

    if fact_check_input:
        if parts:
            parts.append("---")
            parts.append("")

        text_message, _ = await fact_check_text(fact_check_input)
        parts.append(text_message)
    elif not parts:
        # Neither vision nor OCR produced useful content
        if vision_analysis:
            parts.append(f"🖼️ I analyzed this image:\n\n_{vision_analysis[:500]}_\n\n"
                         "I didn't find specific factual claims to verify. "
                         "If there's a claim about this image, try sending it as text!")
        else:
            parts.append(
                "🖼️ I wasn't able to analyze this image. "
                "If there's a claim about it, try sending the claim as text and I'll check it!"
            )

    return "\n".join(parts)


def _needs_escalation(analysis: str) -> bool:
    """Escalate when primary analysis is weak/ambiguous."""
    if not analysis:
        return True

    normalized = analysis.lower()
    weak_markers = (
        "can't determine",
        "cannot determine",
        "unclear",
        "not enough context",
        "unable to",
        "insufficient detail",
    )
    if any(marker in normalized for marker in weak_markers):
        return True

    # Extremely short responses are often too thin for reliable claim extraction.
    return len(analysis.strip()) < 220
