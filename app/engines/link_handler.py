"""Link fact-check handler -- extract article content, check domain credibility, fact-check claims."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from tavily import AsyncTavilyClient

from app.config import TAVILY_API_KEY
from app.engines.text_handler import fact_check_text
from app.sources.allowlists import (
    ALL_NEWS_DOMAINS,
    ALL_OFFICIAL_DOMAINS,
    BLOCKED_DOMAINS,
    FACT_CHECKERS,
)
from app.utils.logger import get_logger

logger = get_logger("engines.link")

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text."""
    return URL_PATTERN.findall(text)


def classify_url(url: str) -> dict:
    """Classify a URL by domain credibility."""
    domain = _extract_domain(url)

    if domain in FACT_CHECKERS or any(fc in url for fc in FACT_CHECKERS):
        return {"domain": domain, "tier": "fact_checker", "trust": "highest", "emoji": "✅"}

    if domain in ALL_OFFICIAL_DOMAINS:
        return {"domain": domain, "tier": "official", "trust": "high", "emoji": "🏛️"}

    if domain in ALL_NEWS_DOMAINS:
        return {"domain": domain, "tier": "news", "trust": "medium-high", "emoji": "📰"}

    if domain in BLOCKED_DOMAINS:
        return {"domain": domain, "tier": "blocked", "trust": "unreliable", "emoji": "🚫"}

    return {"domain": domain, "tier": "general", "trust": "unknown", "emoji": "🌐"}


async def fact_check_link(url: str) -> str:
    """Full link fact-checking pipeline.

    1. Classify the domain
    2. Extract article content via Tavily
    3. Run extracted text through fact-check pipeline
    4. Combine domain assessment + content verdict
    """
    classification = classify_url(url)
    domain = classification["domain"]

    parts: list[str] = []

    if classification["tier"] == "blocked":
        parts.append(f"🔗 *Link from:* _{domain}_")
        parts.append("")
        parts.append(
            "🚫 *Warning:* This domain is on our blocklist of known unreliable sources. "
            "Content from this site has frequently been found to be inaccurate."
        )
        parts.append("")
        parts.append("💡 _Look for the same story on established news outlets for reliable information._")
        return "\n".join(parts)

    if classification["tier"] == "fact_checker":
        parts.append(f"🔗 *Link from:* _{domain}_")
        parts.append("")
        parts.append(
            "✅ This is a recognized fact-checking organization. "
            "Their verdicts are generally reliable and follow IFCN standards."
        )
        return "\n".join(parts)

    article_text = await _extract_article(url)

    if not article_text:
        parts.append(f"🔗 *Link from:* _{domain}_")
        parts.append("")
        parts.append(
            "I couldn't extract the article content. "
            "Try copying the key claims from the article and sending them as text!"
        )
        return "\n".join(parts)

    parts.append(f"📝 *Checking claims from this article:*")
    parts.append("")

    text_message, _ = await fact_check_text(article_text[:3000])
    parts.append(text_message)

    return "\n".join(parts)


async def _extract_article(url: str) -> str:
    """Extract article text content using Tavily's extract feature."""
    try:
        client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
        response = await client.extract(urls=[url])

        results = response.get("results", [])
        if results:
            return results[0].get("raw_content", "")[:3000]
        return ""

    except Exception:
        logger.exception("Article extraction failed for: %s", url)
        return ""


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""
