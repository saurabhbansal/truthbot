"""Audio/voice note fact-check handler -- Gemini native audio analysis."""

from __future__ import annotations

import asyncio
import os
import tempfile

from google.genai import types
from openai import AsyncOpenAI

from app.config import GEMINI_PRO_MODEL, OPENAI_API_KEY
from app.engines.gemini_client import client as gemini_client
from app.engines.text_handler import fact_check_text
from app.utils.logger import get_logger

logger = get_logger("engines.audio")
_openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

_AUDIO_PROMPT = (
    "Analyze this audio recording thoroughly. Provide:\n\n"
    "1. **Transcription**: Transcribe ALL spoken content exactly. "
    "If the audio is in Hindi or another non-English language, provide both "
    "the original language transcription and an English translation.\n"
    "2. **Speaker identification**: Note if there are multiple speakers.\n"
    "3. **Factual claims**: List every factual claim made in the audio.\n"
    "4. **Context**: Note any background sounds, music, or audio quality issues "
    "that might indicate the audio has been edited or is AI-generated.\n\n"
    "Be thorough and factual."
)


async def fact_check_audio(audio_bytes: bytes, caption: str = "") -> str:
    """Full audio fact-checking pipeline using Gemini native audio analysis."""
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.ogg")
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        transcript = await _analyze_audio_with_gemini(audio_path)
        if not transcript:
            transcript = await _transcribe_audio_with_openai(audio_path)

    if not transcript:
        return (
            "🎙️ I wasn't able to process this audio. "
            "If there's a specific claim, try typing it out as text and I'll fact-check it!"
        )

    fact_check_input = ""
    if caption:
        fact_check_input = caption
    fact_check_input = f"{fact_check_input}\n\nAudio transcription and analysis: {transcript}".strip()

    parts: list[str] = ["🎙️ *Checking claims from this audio:*", ""]
    text_message, _ = await fact_check_text(fact_check_input[:4000])
    parts.append(text_message)
    return "\n".join(parts)


async def _analyze_audio_with_gemini(audio_path: str) -> str:
    """Analyze audio natively with Gemini 2.5 Pro."""
    try:
        uploaded_file = await asyncio.to_thread(
            gemini_client.files.upload, file=audio_path
        )

        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model=GEMINI_PRO_MODEL,
            contents=[_AUDIO_PROMPT, uploaded_file],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2000,
            ),
        )

        result = response.text or ""
        logger.info("Gemini audio analysis: %d chars", len(result))

        try:
            await asyncio.to_thread(gemini_client.files.delete, name=uploaded_file.name)
        except Exception:
            pass

        return result.strip()
    except Exception:
        logger.exception("Gemini audio analysis failed")
        return ""


async def _transcribe_audio_with_openai(audio_path: str) -> str:
    """Fallback transcription using OpenAI when Gemini audio fails."""
    try:
        with open(audio_path, "rb") as f:
            transcript = await _openai_client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=f,
            )
        text = transcript.text.strip() if transcript.text else ""
        logger.info("OpenAI audio fallback transcription: %d chars", len(text))
        return text
    except Exception:
        logger.exception("OpenAI audio fallback transcription failed")
        return ""
