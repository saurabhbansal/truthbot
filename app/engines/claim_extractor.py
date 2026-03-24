"""LLM-powered claim extraction from text content."""

from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.utils.logger import get_logger

logger = get_logger("engines.claims")

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

EXTRACTION_PROMPT = """You are a claim extraction specialist. Your job is to identify specific, verifiable factual claims from the given text.

Rules:
- Extract ONLY factual claims that can be verified (not opinions or subjective statements)
- Each claim should be a single, self-contained statement
- Preserve the original meaning EXACTLY — do not add, remove, soften, or strengthen any information
- Do NOT reframe or editorialize claims. Extract them as stated, even if they seem absurd or offensive
- If the text contains no verifiable claims, return an empty claims list
- Return claims in the language they appear in (if Hindi, keep Hindi)
- Maximum 5 claims per message
- Even simple health claims like "X cures Y" are verifiable claims — extract them
- Opinions ("Modi is the best PM") are NOT verifiable — skip them. But factual claims embedded in opinions ("Modi built 10 million houses") ARE verifiable — extract the factual part only

Return a JSON object with a "claims" key containing an array of strings.

Example: {{"claims": ["NASA discovered a second moon orbiting Earth", "The discovery was made on March 15, 2026"]}}

If no verifiable claims found: {{"claims": []}}

TEXT TO ANALYZE:
{text}"""


async def extract_claims(text: str) -> list[str]:
    """Extract verifiable factual claims from text using LLM."""
    try:
        response = await _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You extract factual claims from text. Always respond with valid JSON."},
                {"role": "user", "content": EXTRACTION_PROMPT.format(text=text)},
            ],
            temperature=0.1,
            max_tokens=500,
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

        claims = [str(c).strip() for c in claims if c][:5]
        logger.info("Extracted %d claims from text (%d chars)", len(claims), len(text))
        return claims

    except Exception:
        logger.exception("Claim extraction failed")
        return [text[:500]]
