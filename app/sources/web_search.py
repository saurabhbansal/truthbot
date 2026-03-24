"""Layer 4: General web search -- low trust, corroboration only."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from tavily import AsyncTavilyClient

from app.config import TAVILY_API_KEY
from app.sources.allowlists import BLOCKED_DOMAINS, ALL_NEWS_DOMAINS, ALL_OFFICIAL_DOMAINS
from app.utils.logger import get_logger

logger = get_logger("sources.web")


@dataclass
class WebSearchResult:
    title: str
    url: str
    content: str
    domain: str
    score: float
    is_blocked: bool


async def search_web(claim: str) -> list[WebSearchResult]:
    """General web search with credibility filtering.

    Results from this layer are NEVER cited directly in verdicts.
    They provide context only.
    """
    try:
        client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
        response = await client.search(
            query=claim,
            search_depth="basic",
            exclude_domains=list(BLOCKED_DOMAINS),
            max_results=10,
        )

        results: list[WebSearchResult] = []
        for r in response.get("results", []):
            url = r.get("url", "")
            domain = _extract_domain(url)
            is_blocked = domain in BLOCKED_DOMAINS

            if is_blocked:
                continue

            results.append(
                WebSearchResult(
                    title=r.get("title", ""),
                    url=url,
                    content=r.get("content", ""),
                    domain=domain,
                    score=r.get("score", 0.0),
                    is_blocked=False,
                )
            )

        logger.info("Web search: query=%r → %d results", claim[:60], len(results))
        return results

    except Exception:
        logger.exception("Web search error for: %s", claim[:60])
        return []


def classify_domain(domain: str) -> str:
    """Classify a domain into a trust layer."""
    if domain in ALL_OFFICIAL_DOMAINS:
        return "official"
    if domain in ALL_NEWS_DOMAINS:
        return "news"
    if domain in BLOCKED_DOMAINS:
        return "blocked"
    return "general"


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""
