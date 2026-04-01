"""Shared Gemini API client for all engines."""

from __future__ import annotations

import os

from google import genai

from app.config import GEMINI_API_KEY
from app.utils.logger import get_logger

logger = get_logger("engines.gemini_client")

# Keep Gemini client credential path deterministic when both keys exist in env.
if os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    logger.warning(
        "Both GOOGLE_API_KEY and GEMINI_API_KEY detected. Removing GOOGLE_API_KEY for deterministic Gemini SDK auth."
    )
    os.environ.pop("GOOGLE_API_KEY", None)

client = genai.Client(api_key=GEMINI_API_KEY)
