"""LLM-powered claim extraction from text content."""

from __future__ import annotations

import json
import re

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.utils.logger import get_logger

logger = get_logger("engines.claims")

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

MAX_INPUT_LENGTH = 8000

EXTRACTION_PROMPT = """You are a claim extraction specialist. Your job is to identify specific, verifiable factual claims from the given text.

Rules:
- Extract ONLY factual claims that can be verified (not opinions or subjective statements)
- Each claim should be a single, self-contained statement
- Preserve the original meaning EXACTLY — do not add, remove, soften, or strengthen any information
- Do NOT reframe or editorialize claims. Extract them as stated, even if they seem absurd or offensive
- If the text contains no verifiable claims, return an empty claims list
- Return claims in the language they appear in (if Hindi, keep Hindi)
- Maximum 12 claims per message
- Even simple health claims like "X cures Y" are verifiable claims — extract them
- Opinions ("Modi is the best PM") are NOT verifiable — skip them. But factual claims embedded in opinions ("Modi built 10 million houses") ARE verifiable — extract the factual part only

Return a JSON object with a "claims" key containing an array of strings.

Example: {{"claims": ["NASA discovered a second moon orbiting Earth", "The discovery was made on March 15, 2026"]}}

If no verifiable claims found: {{"claims": []}}

TEXT TO ANALYZE:
{text}"""

TRANSLATION_PROMPT = """Translate the following factual claim to clear, plain English.

Rules:
- Preserve meaning exactly (no added/removed facts).
- Keep names, numbers, dates, units, and quoted phrases unchanged.
- If the text is already English, return it unchanged.
- Return only the translated sentence.

CLAIM:
{text}"""


async def extract_claims(text: str) -> list[str]:
    """Extract verifiable factual claims from text using LLM."""
    if len(text) > MAX_INPUT_LENGTH:
        logger.warning("Input text truncated from %d to %d chars", len(text), MAX_INPUT_LENGTH)
        text = text[:MAX_INPUT_LENGTH]

    try:
        response = await _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You extract factual claims from text. Always respond with valid JSON."},
                {"role": "user", "content": EXTRACTION_PROMPT.format(text=text)},
            ],
            temperature=0.1,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "[]"
        parsed = json.loads(content)

        if isinstance(parsed, list):
            claims = parsed
        elif isinstance(parsed, dict):
            claims = parsed.get("claims", parsed.get("results", []))
        else:
            claims = []

        claims = [str(c).strip() for c in claims if c][:12]
        logger.info("Extracted %d claims from text (%d chars)", len(claims), len(text))
        return claims

    except Exception:
        logger.exception("Claim extraction failed")
        return []


def filter_grounded_claims(source_text: str, claims: list[str]) -> list[str]:
    """Keep only claims that are grounded in the provided source text.

    Uses a relaxed matching threshold (70% token overlap) to avoid
    discarding legitimate claims that the LLM paraphrased slightly.
    """
    if not source_text or not claims:
        return claims

    normalized_source = _normalize_for_match(source_text)
    source_tokens = set(normalized_source.split())

    grounded: list[str] = []
    for claim in claims:
        normalized_claim = _normalize_for_match(claim)
        if not normalized_claim:
            continue

        if normalized_claim in normalized_source:
            grounded.append(claim)
            continue

        claim_tokens = normalized_claim.split()
        if len(claim_tokens) < 3:
            grounded.append(claim)
            continue

        overlap = sum(1 for t in claim_tokens if t in source_tokens)
        overlap_ratio = overlap / len(claim_tokens)
        if overlap_ratio >= 0.70:
            grounded.append(claim)

    if not grounded and claims:
        logger.warning(
            "Grounding filter dropped all %d claims — returning originals as fallback",
            len(claims),
        )
        return claims

    return grounded


def _normalize_for_match(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def translate_claim_to_english(text: str) -> str:
    """Translate a claim to English for consistent source searching."""
    if not text.strip():
        return text
    try:
        response = await _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You translate claims to English exactly."},
                {"role": "user", "content": TRANSLATION_PROMPT.format(text=text)},
            ],
            temperature=0,
            max_tokens=300,
        )
        translated = (response.choices[0].message.content or "").strip()
        return translated or text
    except Exception:
        logger.exception("Claim translation failed")
        return text
