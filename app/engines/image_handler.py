"""Image fact-check handler -- GPT-4o Vision analysis, OCR, and text fact-checking."""

from __future__ import annotations

import asyncio
import base64

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, OPENAI_VERDICT_MODEL
from app.engines.ocr import extract_text_from_image
from app.engines.text_handler import fact_check_text
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


async def _analyze_image_with_vision(image_bytes: bytes) -> str:
    """Send image to GPT-4o Vision for comprehensive visual analysis."""
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    try:
        response = await _client.chat.completions.create(
            model=OPENAI_VERDICT_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            max_tokens=1500,
            temperature=0.1,
        )

        content = response.choices[0].message.content or ""
        logger.info("Vision analysis: %d chars", len(content))
        return content.strip()

    except Exception:
        logger.exception("GPT-4o Vision analysis failed")
        return ""


async def fact_check_image(image_bytes: bytes, caption: str = "") -> str:
    """Full image fact-checking pipeline.

    1. Run GPT-4o Vision analysis + OCR in parallel
    2. Check for AI-generated/manipulated content from vision analysis
    3. Combine vision description + OCR text + caption for fact-checking
    """
    vision_task = _analyze_image_with_vision(image_bytes)
    ocr_task = extract_text_from_image(image_bytes)

    vision_analysis, ocr_text = await asyncio.gather(vision_task, ocr_task)

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
