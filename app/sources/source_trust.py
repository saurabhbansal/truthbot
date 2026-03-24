"""Source trust scoring -- aggregates evidence from all 4 layers into a confidence score."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.sources.fact_check_db import FactCheckResult, search_claims
from app.sources.official_sources import OfficialSourceResult, search_official
from app.sources.news_sources import NewsSourceResult, search_news
from app.sources.web_search import WebSearchResult, search_web
from app.utils.logger import get_logger

logger = get_logger("sources.trust")

# Trust weights by layer
LAYER_WEIGHTS = {
    "fact_check": 1.0,
    "official": 0.85,
    "news": 0.6,
    "web": 0.2,
}


@dataclass
class SourceEvidence:
    """All evidence collected from all 4 source layers for a single claim."""

    claim: str
    fact_checks: list[FactCheckResult] = field(default_factory=list)
    official_results: list[OfficialSourceResult] = field(default_factory=list)
    news_results: list[NewsSourceResult] = field(default_factory=list)
    web_results: list[WebSearchResult] = field(default_factory=list)
    confidence: float = 0.0
    highest_layer: str = "none"

    @property
    def has_fact_check(self) -> bool:
        return len(self.fact_checks) > 0

    @property
    def has_official(self) -> bool:
        return len(self.official_results) > 0

    @property
    def has_news(self) -> bool:
        return len(self.news_results) > 0

    @property
    def total_sources(self) -> int:
        return (
            len(self.fact_checks)
            + len(self.official_results)
            + len(self.news_results)
            + len(self.web_results)
        )

    def citable_sources(self) -> list[dict]:
        """Return sources suitable for citation in the verdict (Layer 1-3 only)."""
        sources: list[dict] = []

        for fc in self.fact_checks:
            sources.append({
                "layer": "fact_check",
                "title": f"{fc.publisher}: {fc.rating}",
                "url": fc.url,
                "publisher": fc.publisher,
                "weight": LAYER_WEIGHTS["fact_check"],
            })

        for off in self.official_results:
            sources.append({
                "layer": "official",
                "title": off.title,
                "url": off.url,
                "publisher": off.domain,
                "weight": LAYER_WEIGHTS["official"],
            })

        for news in self.news_results:
            sources.append({
                "layer": "news",
                "title": news.title,
                "url": news.url,
                "publisher": news.domain,
                "weight": LAYER_WEIGHTS["news"],
            })

        return sources


async def gather_evidence(claim: str) -> SourceEvidence:
    """Search all 4 source layers in parallel and compute confidence."""
    evidence = SourceEvidence(claim=claim)

    fact_checks, official, news, web = await asyncio.gather(
        search_claims(claim),
        search_official(claim),
        search_news(claim),
        search_web(claim),
        return_exceptions=True,
    )

    if isinstance(fact_checks, list):
        evidence.fact_checks = fact_checks
    else:
        logger.error("Fact check search failed: %s", fact_checks)

    if isinstance(official, list):
        evidence.official_results = official
    else:
        logger.error("Official source search failed: %s", official)

    if isinstance(news, list):
        evidence.news_results = news
    else:
        logger.error("News source search failed: %s", news)

    if isinstance(web, list):
        evidence.web_results = web
    else:
        logger.error("Web search failed: %s", web)

    evidence.confidence = _compute_confidence(evidence)
    evidence.highest_layer = _highest_layer(evidence)

    logger.info(
        "Evidence gathered: claim=%r fact_checks=%d official=%d news=%d web=%d confidence=%.2f",
        claim[:60],
        len(evidence.fact_checks),
        len(evidence.official_results),
        len(evidence.news_results),
        len(evidence.web_results),
        evidence.confidence,
    )

    return evidence


def _compute_confidence(evidence: SourceEvidence) -> float:
    """Compute overall confidence based on which layers returned results."""
    if evidence.has_fact_check:
        base = 0.90
    elif evidence.has_official:
        base = 0.80
    elif evidence.has_news:
        base = 0.65
    elif len(evidence.web_results) > 0:
        base = 0.35
    else:
        return 0.1

    # Bonus for multiple layers agreeing
    layers_with_results = sum([
        evidence.has_fact_check,
        evidence.has_official,
        evidence.has_news,
        len(evidence.web_results) > 0,
    ])
    layer_bonus = min(0.10, (layers_with_results - 1) * 0.05)

    # Bonus for multiple sources within a layer (deduplication signal)
    source_count = evidence.total_sources
    source_bonus = min(0.05, (source_count - 1) * 0.01)

    return min(1.0, base + layer_bonus + source_bonus)


def _highest_layer(evidence: SourceEvidence) -> str:
    if evidence.has_fact_check:
        return "fact_check"
    if evidence.has_official:
        return "official"
    if evidence.has_news:
        return "news"
    if len(evidence.web_results) > 0:
        return "web"
    return "none"
