from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_logger = logging.getLogger("truthbot.config")


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


# WhatsApp Cloud API
WHATSAPP_ACCESS_TOKEN: str = _require("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID: str = _require("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_BUSINESS_ACCOUNT_ID: str = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
META_APP_SECRET: str = os.getenv("META_APP_SECRET", "")
WHATSAPP_VERIFY_TOKEN: str = _require("WHATSAPP_VERIFY_TOKEN")

WHATSAPP_API_URL: str = (
    f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
)
WHATSAPP_MEDIA_URL: str = "https://graph.facebook.com/v22.0"

# OpenAI (used for image Vision analysis as backup)
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")

# Gemini (primary LLM for verdicts, claims, video/audio)
GEMINI_API_KEY: str = _require("GEMINI_API_KEY")
GEMINI_PRO_MODEL: str = "gemini-2.5-pro"
GEMINI_FLASH_MODEL: str = "gemini-2.5-flash"

# Tavily
TAVILY_API_KEY: str = _require("TAVILY_API_KEY")

# Google Cloud
GOOGLE_API_KEY: str = _require("GOOGLE_API_KEY")
GOOGLE_FACT_CHECK_URL: str = (
    "https://factchecktools.googleapis.com/v1alpha1/claims:search"
)

# Media size limits
MAX_IMAGE_SIZE: int = 10 * 1024 * 1024  # 10 MB
MAX_VIDEO_SIZE: int = 16 * 1024 * 1024  # 16 MB (WhatsApp's own limit)
MAX_VIDEO_DOWNLOAD_SIZE: int = 50 * 1024 * 1024  # 50 MB for yt-dlp downloads
MAX_AUDIO_SIZE: int = 16 * 1024 * 1024  # 16 MB
VIDEO_DOWNLOAD_TIMEOUT: int = int(os.getenv("VIDEO_DOWNLOAD_TIMEOUT", "60"))

# App settings
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "truthbot.db")
PORT: int = int(os.getenv("PORT", "8000"))
RETENTION_DAYS_DAILY_USAGE: int = int(os.getenv("RETENTION_DAYS_DAILY_USAGE", "35"))
RETENTION_DAYS_USAGE_STATS: int = int(os.getenv("RETENTION_DAYS_USAGE_STATS", "90"))
RETENTION_DAYS_FEEDBACK: int = int(os.getenv("RETENTION_DAYS_FEEDBACK", "90"))

if not META_APP_SECRET:
    _logger.warning("META_APP_SECRET not set — webhook signature verification is disabled")
