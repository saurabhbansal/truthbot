"""Video fact-check handler -- ffmpeg frame/audio extraction, GPT-4o Vision, Whisper transcription."""

from __future__ import annotations

import asyncio
import base64
import os
import tempfile
from pathlib import Path

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, OPENAI_VERDICT_MODEL
from app.engines.text_handler import fact_check_text
from app.utils.logger import get_logger

logger = get_logger("engines.video")

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

MAX_FRAMES = 4
MAX_AUDIO_DURATION_S = 120
MAX_AUDIO_SIZE = 25 * 1024 * 1024  # Whisper API limit

_FRAME_PROMPT = (
    "These are frames extracted from a video. Analyze them carefully.\n\n"
    "1. **Description**: What does the video show? Describe people, objects, text overlays, "
    "logos, screenshots, or any visual content across the frames.\n"
    "2. **Text transcription**: If there is ANY text visible in any frame (headlines, captions, "
    "watermarks, screenshots of messages), transcribe it exactly.\n"
    "3. **Claims**: If the video frames make or imply any factual claims (through text, context, "
    "or visual content), list each claim clearly.\n"
    "4. **AI assessment**: Do these frames appear to be from an AI-generated video, digitally "
    "manipulated, or a deepfake? Note any visual artifacts or inconsistencies.\n"
    "5. **Continuity**: Note if the frames seem to tell a coherent story or if there are "
    "suspicious jumps/edits.\n\n"
    "Be thorough and factual. Do not speculate beyond what is visible."
)


async def _extract_frames(video_path: str, output_dir: str) -> list[str]:
    """Extract evenly-spaced frames from a video using ffmpeg."""
    duration = await _get_video_duration(video_path)
    if duration <= 0:
        duration = 10.0

    interval = max(duration / (MAX_FRAMES + 1), 1.0)
    timestamps = [interval * (i + 1) for i in range(MAX_FRAMES)]

    frame_paths: list[str] = []
    for i, ts in enumerate(timestamps):
        out_path = os.path.join(output_dir, f"frame_{i}.jpg")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-ss", str(ts), "-i", video_path,
            "-frames:v", "1", "-q:v", "3", "-y", out_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=15)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            frame_paths.append(out_path)

    if not frame_paths:
        out_path = os.path.join(output_dir, "frame_0.jpg")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", video_path,
            "-frames:v", "1", "-q:v", "3", "-y", out_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=15)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            frame_paths.append(out_path)

    return frame_paths


async def _extract_audio(video_path: str, output_dir: str) -> str | None:
    """Extract audio track from video using ffmpeg, limited to MAX_AUDIO_DURATION_S."""
    audio_path = os.path.join(output_dir, "audio.mp3")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", video_path,
        "-t", str(MAX_AUDIO_DURATION_S),
        "-vn", "-acodec", "libmp3lame", "-ab", "64k",
        "-ar", "16000", "-ac", "1",
        "-y", audio_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await asyncio.wait_for(proc.wait(), timeout=30)

    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
        if os.path.getsize(audio_path) > MAX_AUDIO_SIZE:
            logger.warning("Audio file too large for Whisper: %d bytes", os.path.getsize(audio_path))
            return None
        return audio_path
    return None


async def _get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", video_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        import json
        data = json.loads(stdout.decode())
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        logger.debug("Could not determine video duration")
        return 0.0


async def _analyze_frames_with_vision(frame_paths: list[str]) -> str:
    """Send extracted frames to GPT-4o Vision for analysis."""
    content: list[dict] = [{"type": "text", "text": _FRAME_PROMPT}]

    for fp in frame_paths:
        with open(fp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"},
        })

    try:
        response = await _client.chat.completions.create(
            model=OPENAI_VERDICT_MODEL,
            messages=[{"role": "user", "content": content}],
            max_tokens=1500,
            temperature=0.1,
        )
        result = response.choices[0].message.content or ""
        logger.info("Video vision analysis: %d chars from %d frames", len(result), len(frame_paths))
        return result.strip()
    except Exception:
        logger.exception("GPT-4o Vision video analysis failed")
        return ""


async def _transcribe_audio(audio_path: str) -> str:
    """Transcribe audio using OpenAI Whisper API (auto-detects language)."""
    try:
        with open(audio_path, "rb") as f:
            transcript = await _client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=f,
            )
        text = transcript.text.strip() if transcript.text else ""
        logger.info("Whisper transcription: %d chars", len(text))
        return text
    except Exception:
        logger.exception("Whisper transcription failed")
        return ""


async def analyze_video_file(video_path: str, caption: str = "") -> str:
    """Core video analysis pipeline that works on a file path.

    Used by both uploaded-video and video-link-download flows.
    1. Extract frames + audio in parallel via ffmpeg
    2. Analyze frames with GPT-4o Vision + transcribe audio with Whisper in parallel
    3. Check for AI-generated/manipulated content
    4. Combine all text sources and run fact-checking pipeline
    """
    tmpdir = os.path.dirname(video_path)

    frame_task = _extract_frames(video_path, tmpdir)
    audio_task = _extract_audio(video_path, tmpdir)

    try:
        frame_paths, audio_out = await asyncio.gather(frame_task, audio_task)
    except Exception:
        logger.exception("ffmpeg extraction failed")
        frame_paths, audio_out = [], None

    async def _noop() -> str:
        return ""

    vision_task = (
        _analyze_frames_with_vision(frame_paths)
        if frame_paths else _noop()
    )
    transcribe_task = (
        _transcribe_audio(audio_out)
        if audio_out else _noop()
    )

    try:
        vision_analysis, transcript = await asyncio.gather(vision_task, transcribe_task)
    except Exception:
        logger.exception("Video analysis/transcription failed")
        vision_analysis, transcript = "", ""

    parts: list[str] = []

    ai_keywords = ("ai-generated", "ai generated", "artificially generated",
                   "digitally manipulated", "deepfake", "appears to be generated")
    vision_lower = vision_analysis.lower()
    if any(kw in vision_lower for kw in ai_keywords):
        if any(w in vision_lower for w in ("likely ai", "appears to be ai", "appears to be generated",
                                            "is ai-generated", "is ai generated")):
            parts.append("🤖 *POSSIBLE AI-GENERATED VIDEO*")
            parts.append("")
            parts.append(
                "This video shows signs of being AI-generated or digitally manipulated. "
                "Always verify the source before sharing."
            )
            parts.append("")

    fact_check_input = ""
    if caption:
        fact_check_input = caption
    if transcript:
        label = "Audio transcript" if fact_check_input else ""
        if label:
            fact_check_input = f"{fact_check_input}\n\n{label}: {transcript}"
        else:
            fact_check_input = transcript
    if vision_analysis:
        fact_check_input = f"{fact_check_input}\n\nVideo visual analysis: {vision_analysis}".strip()

    if fact_check_input:
        if parts:
            parts.append("---")
            parts.append("")
        text_message, _ = await fact_check_text(fact_check_input)
        parts.append(text_message)
    elif not parts:
        if vision_analysis:
            parts.append(f"📹 I analyzed this video:\n\n_{vision_analysis[:500]}_\n\n"
                         "I didn't find specific factual claims to verify. "
                         "If there's a claim in this video, try sending it as text!")
        else:
            parts.append(
                "📹 I wasn't able to extract content from this video. "
                "If there's a specific claim, try typing it out as text and I'll fact-check it!"
            )

    return "\n".join(parts)


async def fact_check_video(video_bytes: bytes, caption: str = "") -> str:
    """Full video fact-checking pipeline for uploaded videos (bytes input)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "video.mp4")
        Path(video_path).write_bytes(video_bytes)
        return await analyze_video_file(video_path, caption=caption)
