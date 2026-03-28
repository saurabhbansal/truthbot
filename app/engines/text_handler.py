"""Text fact-check handler -- orchestrates the full pipeline for text messages."""

from __future__ import annotations

import asyncio
import re

from app.engines.claim_extractor import (
    extract_claims,
    filter_grounded_claims,
    translate_claim_to_english,
)
from app.engines.verdict_engine import Verdict, produce_verdict
from app.sources.source_trust import gather_evidence
from app.verdict.formatter import format_multi_verdict
from app.utils.logger import get_logger

logger = get_logger("engines.text")

_GROUP_TERMS = (
    "hindu",
    "muslim",
    "christian",
    "sikh",
    "dalit",
    "brahmin",
    "upper caste",
    "lower caste",
    "religion",
    "community",
)

_GENERALIZATION_TERMS = (
    "under attack",
    "are dangerous",
    "want to destroy",
    "are taking over",
    "hate us",
    "are against",
    "enemy",
    "traitor",
)

_BROAD_CLAIM_FALLBACK = (
    "I understand this is a sensitive concern.\n\n"
    "This statement is too broad to verify as written. I can't fact-check general claims about whole communities.\n\n"
    "Please share one specific incident with what happened, where, when, and a source link, and I'll verify it using official reports and reliable news."
)


def _is_broad_sensitive_generalization(text: str) -> bool:
    lowered = text.lower()
    if not any(term in lowered for term in _GROUP_TERMS):
        return False
    if any(term in lowered for term in _GENERALIZATION_TERMS):
        return True
    # Catch common "<group> are ..." blanket statements.
    return bool(re.search(r"\b(hindus?|muslims?|christians?|sikhs?|dalits?)\b\s+\b(are|is)\b", lowered))


async def fact_check_text(text: str) -> tuple[str, list[Verdict]]:
    """Full text fact-checking pipeline.

    1. Extract verifiable claims from text
    2. Gather evidence for each claim (all 4 source layers in parallel)
    3. Produce verdict for each claim
    4. Format into WhatsApp message

    Returns (formatted_message, list_of_verdicts).
    """
    if not text or not text.strip():
        return (
            "Please send me a message, image, video, or link to fact-check!",
            [],
        )

    if _is_broad_sensitive_generalization(text):
        return _BROAD_CLAIM_FALLBACK, []

    claims = await extract_claims(text)
    claims = filter_grounded_claims(text, claims)

    if not claims:
        return (
            "🤔 I couldn't isolate any clear factual claims from this content. "
            "Please paste the exact claim text you want checked, for example:\n\n"
            "• _\"NASA discovered a new planet\"_\n"
            "• _\"RBI increased interest rates to 8%\"_\n"
            "• _\"Drinking hot water cures COVID\"_",
            [],
        )

    logger.info("Processing %d claims", len(claims))

    english_claims_raw = await asyncio.gather(
        *[translate_claim_to_english(claim) for claim in claims],
        return_exceptions=True,
    )
    # Fall back to original claim text if translation failed
    english_claims = [
        orig if isinstance(trans, BaseException) else trans
        for orig, trans in zip(claims, english_claims_raw)
    ]

    evidence_raw = await asyncio.gather(
        *[gather_evidence(claim) for claim in english_claims],
        return_exceptions=True,
    )

    # Only proceed with claims whose evidence gathering succeeded
    valid_pairs = [
        (claim, evidence)
        for claim, evidence in zip(english_claims, evidence_raw)
        if not isinstance(evidence, BaseException)
    ]
    if not valid_pairs:
        logger.error("All evidence gathering failed")
        return (
            "I'm having trouble verifying this right now. Please try again in a moment!",
            [],
        )

    valid_claims, valid_evidence = zip(*valid_pairs)

    verdicts_raw = await asyncio.gather(
        *[
            produce_verdict(claim, evidence)
            for claim, evidence in zip(valid_claims, valid_evidence)
        ],
        return_exceptions=True,
    )

    verdicts = [v for v in verdicts_raw if not isinstance(v, BaseException)]
    if not verdicts:
        logger.error("All verdict production failed")
        return (
            "I'm having trouble verifying this right now. Please try again in a moment!",
            [],
        )

    message = format_multi_verdict(verdicts)

    return message, verdicts
