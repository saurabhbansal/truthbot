"""Text fact-check handler -- orchestrates the full pipeline for text messages."""

from __future__ import annotations

import asyncio

from app.engines.claim_extractor import extract_claims
from app.engines.verdict_engine import Verdict, produce_verdict
from app.sources.source_trust import gather_evidence
from app.verdict.formatter import format_multi_verdict
from app.utils.logger import get_logger

logger = get_logger("engines.text")


async def fact_check_text(text: str) -> tuple[str, list[Verdict]]:
    """Full text fact-checking pipeline.

    1. Extract verifiable claims from text
    2. Gather evidence for each claim (all 4 source layers in parallel)
    3. Produce verdict for each claim
    4. Format into WhatsApp message

    Returns (formatted_message, list_of_verdicts).
    """
    claims = await extract_claims(text)

    if not claims:
        return (
            "🤔 I couldn't find any specific factual claims to check in this message. "
            "Try sending a specific claim like:\n\n"
            "• _\"NASA discovered a new planet\"_\n"
            "• _\"RBI increased interest rates to 8%\"_\n"
            "• _\"Drinking hot water cures COVID\"_",
            [],
        )

    logger.info("Processing %d claims", len(claims))

    evidence_list = await asyncio.gather(
        *[gather_evidence(claim) for claim in claims]
    )

    verdicts = await asyncio.gather(
        *[
            produce_verdict(claim, evidence)
            for claim, evidence in zip(claims, evidence_list)
        ]
    )

    verdicts = list(verdicts)
    message = format_multi_verdict(verdicts)

    return message, verdicts
