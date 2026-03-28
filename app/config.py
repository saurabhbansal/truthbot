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

# OpenAI
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_VERDICT_MODEL: str = os.getenv("OPENAI_VERDICT_MODEL", "gpt-4o")

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

# App settings
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "truthbot.db")
PORT: int = int(os.getenv("PORT", "8000"))

if not META_APP_SECRET:
    _logger.warning("META_APP_SECRET not set — webhook signature verification is disabled")
