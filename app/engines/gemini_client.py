"""Shared Gemini API client for all engines."""

from __future__ import annotations

from google import genai

from app.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)
