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

    # Keep user-visible output in English while accepting non-English inputs.
    english_claims = await asyncio.gather(
        *[translate_claim_to_english(claim) for claim in claims]
    )

    evidence_list = await asyncio.gather(
        *[gather_evidence(claim) for claim in english_claims]
    )

    verdicts = await asyncio.gather(
        *[
            produce_verdict(claim, evidence)
            for claim, evidence in zip(english_claims, evidence_list)
        ]
    )

    verdicts = list(verdicts)
    message = format_multi_verdict(verdicts)

    return message, verdicts
