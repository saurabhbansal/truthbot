"""Layer 1: Google Fact Check Tools API -- highest trust source."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import GOOGLE_API_KEY, GOOGLE_FACT_CHECK_URL
from app.utils.logger import get_logger

logger = get_logger("sources.fact_check")


@dataclass
class FactCheckResult:
    claim_text: str
    claimant: str
    rating: str
    url: str
    publisher: str
    language: str


async def search_claims(query: str, language: str = "en") -> list[FactCheckResult]:
    """Search Google Fact Check API for existing fact-checks of a claim.

    Returns a list of fact-check results from IFCN-certified organizations.
    """
    params = {
        "query": query,
        "key": GOOGLE_API_KEY,
        "languageCode": language,
        "pageSize": 10,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(GOOGLE_FACT_CHECK_URL, params=params)

        if resp.status_code != 200:
            logger.error("Fact Check API HTTP %d: %s", resp.status_code, resp.text[:200])
            return []

        data = resp.json()
        if "error" in data:
            logger.error("Fact Check API error: %s", data["error"])
            return []

        results: list[FactCheckResult] = []
        for claim in data.get("claims", []):
            for review in claim.get("claimReview", []):
                results.append(
                    FactCheckResult(
                        claim_text=claim.get("text", ""),
                        claimant=claim.get("claimant", "Unknown"),
                        rating=review.get("textualRating", "Unknown"),
                        url=review.get("url", ""),
                        publisher=review.get("publisher", {}).get("name", "Unknown"),
                        language=review.get("languageCode", language),
                    )
                )

        logger.info(
            "Fact Check API: query=%r → %d results", query[:80], len(results)
        )
        return results

    except Exception:
        logger.exception("Fact Check API error for query: %s", query[:80])
        return []


async def search_image(image_url: str, language: str = "en") -> list[FactCheckResult]:
    """Search Google Fact Check API using an image URL."""
    url = "https://factchecktools.googleapis.com/v1alpha1/claims:imageSearch"
    params = {
        "imageUri": image_url,
        "key": GOOGLE_API_KEY,
        "languageCode": language,
        "pageSize": 10,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            data = resp.json()

        results: list[FactCheckResult] = []
        for claim in data.get("claims", []):
            for review in claim.get("claimReview", []):
                results.append(
                    FactCheckResult(
                        claim_text=claim.get("text", ""),
                        claimant=claim.get("claimant", "Unknown"),
                        rating=review.get("textualRating", "Unknown"),
                        url=review.get("url", ""),
                        publisher=review.get("publisher", {}).get("name", "Unknown"),
                        language=review.get("languageCode", language),
                    )
                )

        logger.info("Fact Check Image API: %d results", len(results))
        return results

    except Exception:
        logger.exception("Fact Check Image API error")
        return []
