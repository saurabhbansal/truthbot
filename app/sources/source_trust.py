"""Source trust scoring -- aggregates evidence from all source layers into a confidence score."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.db.cache import get_cached_evidence, set_cached_evidence
from app.sources.fact_check_db import FactCheckResult, search_claims
from app.sources.official_sources import OfficialSourceResult, search_official
from app.sources.news_sources import NewsSourceResult, search_news
from app.sources.web_search import WebSearchResult
from app.utils.logger import get_logger

logger = get_logger("sources.trust")

LAYER_WEIGHTS = {
    "fact_check": 1.0,
    "official": 0.85,
    "news": 0.6,
    "web": 0.2,
}


@dataclass
class SourceEvidence:
    """All evidence collected from source layers for a single claim."""

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
    """Search source layers and compute confidence.

    Optimizations:
    - Check evidence cache first (24h TTL)
    - Always search Layer 1 (fact-checks, free API)
    - If Layer 1 has strong results, short-circuit (skip Tavily calls)
    - Otherwise search Layers 2+3 in parallel (basic depth to save credits)
    - Layer 4 (general web) is dropped to save Tavily credits
    """
    cached = await get_cached_evidence(claim)
    if cached is not None:
        return cached

    evidence = SourceEvidence(claim=claim)

    fact_checks = await search_claims(claim)
    if isinstance(fact_checks, list):
        evidence.fact_checks = fact_checks
    else:
        logger.error("Fact check search failed: %s", fact_checks)

    if evidence.has_fact_check and len(evidence.fact_checks) >= 2:
        logger.info("Fact-check short-circuit: %d results for %r", len(evidence.fact_checks), claim[:60])
        evidence.confidence = _compute_confidence(evidence)
        evidence.highest_layer = _highest_layer(evidence)
        await set_cached_evidence(claim, evidence)
        return evidence

    official, news = await asyncio.gather(
        search_official(claim),
        search_news(claim),
        return_exceptions=True,
    )

    if isinstance(official, list):
        evidence.official_results = official
    else:
        logger.error("Official source search failed: %s", official)

    if isinstance(news, list):
        evidence.news_results = news
    else:
        logger.error("News source search failed: %s", news)

    evidence.confidence = _compute_confidence(evidence)
    evidence.highest_layer = _highest_layer(evidence)

    logger.info(
        "Evidence gathered: claim=%r fact_checks=%d official=%d news=%d confidence=%.2f",
        claim[:60],
        len(evidence.fact_checks),
        len(evidence.official_results),
        len(evidence.news_results),
        evidence.confidence,
    )

    await set_cached_evidence(claim, evidence)
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

    layers_with_results = sum([
        evidence.has_fact_check,
        evidence.has_official,
        evidence.has_news,
        len(evidence.web_results) > 0,
    ])
    layer_bonus = min(0.10, (layers_with_results - 1) * 0.05)

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
