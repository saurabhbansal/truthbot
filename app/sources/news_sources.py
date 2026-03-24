"""Layer 3: Established news outlets -- search filtered to trusted domains."""

from __future__ import annotations

from dataclasses import dataclass

from tavily import AsyncTavilyClient

from app.config import TAVILY_API_KEY
from app.sources.allowlists import ALL_NEWS_DOMAINS
from app.utils.logger import get_logger

logger = get_logger("sources.news")


@dataclass
class NewsSourceResult:
    title: str
    url: str
    content: str
    domain: str
    score: float


async def search_news(claim: str) -> list[NewsSourceResult]:
    """Search established news outlets for coverage of a claim."""
    try:
        client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
        response = await client.search(
            query=claim,
            search_depth="advanced",
            include_domains=list(ALL_NEWS_DOMAINS)[:20],
            max_results=5,
        )

        results: list[NewsSourceResult] = []
        for r in response.get("results", []):
            url = r.get("url", "")
            domain = _extract_domain(url)
            results.append(
                NewsSourceResult(
                    title=r.get("title", ""),
                    url=url,
                    content=r.get("content", ""),
                    domain=domain,
                    score=r.get("score", 0.0),
                )
            )

        logger.info("News sources: query=%r → %d results", claim[:60], len(results))
        return results

    except Exception:
        logger.exception("News source search error for: %s", claim[:60])
        return []


def _extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()
    except Exception:
        return ""
