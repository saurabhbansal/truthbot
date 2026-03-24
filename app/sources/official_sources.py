"""Layer 2: Official primary sources -- targeted search on .gov, .edu, etc."""

from __future__ import annotations

from dataclasses import dataclass

from tavily import AsyncTavilyClient

from app.config import TAVILY_API_KEY
from app.sources.allowlists import ALL_OFFICIAL_DOMAINS
from app.utils.logger import get_logger

logger = get_logger("sources.official")


@dataclass
class OfficialSourceResult:
    title: str
    url: str
    content: str
    domain: str
    score: float


def _identify_relevant_domains(claim: str) -> list[str]:
    """Identify which official domains are most relevant for a claim."""
    claim_lower = claim.lower()

    domains: list[str] = []

    # Financial claims
    if any(w in claim_lower for w in ("rbi", "rupee", "bank", "interest rate", "currency", "note", "upi", "tax", "gst")):
        domains.extend(["rbi.org.in", "incometaxindia.gov.in", "gst.gov.in", "sebi.gov.in"])

    # Health claims
    if any(w in claim_lower for w in ("health", "cure", "disease", "cancer", "covid", "vaccine", "doctor", "hospital", "medicine", "drug", "treatment")):
        domains.extend(["who.int", "icmr.gov.in", "mohfw.gov.in", "cdc.gov", "nih.gov"])

    # Government policy
    if any(w in claim_lower for w in ("government", "modi", "parliament", "law", "rule", "policy", "scheme", "pension", "aadhaar")):
        domains.extend(["pib.gov.in", "india.gov.in", "mha.gov.in"])

    # Science / space
    if any(w in claim_lower for w in ("nasa", "isro", "space", "moon", "mars", "satellite", "earthquake", "weather", "cyclone", "flood")):
        domains.extend(["isro.gov.in", "nasa.gov", "imd.gov.in"])

    # Academic / research
    if any(w in claim_lower for w in ("study", "research", "university", "professor", "journal", "published", "peer-reviewed")):
        domains.extend(["pubmed.ncbi.nlm.nih.gov", "nature.com", "thelancet.com"])

    if not domains:
        domains = ["pib.gov.in", "who.int", "india.gov.in"]

    return domains[:5]


async def search_official(claim: str) -> list[OfficialSourceResult]:
    """Search official sources for evidence about a claim.

    Uses Tavily with include_domains to restrict to official sites.
    """
    relevant_domains = _identify_relevant_domains(claim)

    try:
        client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
        response = await client.search(
            query=claim,
            search_depth="advanced",
            include_domains=relevant_domains,
            max_results=5,
        )

        results: list[OfficialSourceResult] = []
        for r in response.get("results", []):
            url = r.get("url", "")
            domain = _extract_domain(url)
            results.append(
                OfficialSourceResult(
                    title=r.get("title", ""),
                    url=url,
                    content=r.get("content", ""),
                    domain=domain,
                    score=r.get("score", 0.0),
                )
            )

        logger.info(
            "Official sources: query=%r domains=%s → %d results",
            claim[:60],
            relevant_domains,
            len(results),
        )
        return results

    except Exception:
        logger.exception("Official source search error for: %s", claim[:60])
        return []


def _extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()
    except Exception:
        return ""
