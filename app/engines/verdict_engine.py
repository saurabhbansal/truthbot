"""Core verdict engine -- reasons over evidence to produce a verdict.

Implements the anti-hallucination pipeline:
1. Search first, reason second (never generate claims)
2. Cite only retrieved sources (mandatory citation)
3. Validate source existence
4. Confidence calibration based on source layers
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.sources.source_trust import SourceEvidence
from app.verdict.confidence import VerdictLabel
from app.utils.logger import get_logger

logger = get_logger("engines.verdict")

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


@dataclass
class Verdict:
    label: VerdictLabel
    confidence: float
    summary: str
    explanation: str
    sources: list[dict] = field(default_factory=list)
    partial_truth_pattern: str = ""
    claim: str = ""


VERDICT_PROMPT = """You are TruthBot, a fact-checking assistant. You must produce a verdict for the claim below based ONLY on the evidence provided. You MUST NOT use any knowledge not present in the evidence.

## CRITICAL RULES (Anti-Hallucination):
1. ONLY cite sources from the evidence below. Never invent URLs or source names.
2. If evidence is insufficient, verdict MUST be "UNVERIFIED" — never guess.
3. Every factual statement in your explanation must reference a specific source from the evidence.
4. If sources contradict each other, note the contradiction and lower confidence.
5. Never say "according to multiple sources" — name each source specifically.

## CLAIM:
{claim}

## EVIDENCE FROM VERIFIED SOURCES:

### Layer 1 — Fact-Check Organizations (highest trust):
{fact_check_evidence}

### Layer 2 — Official Sources (government, academic):
{official_evidence}

### Layer 3 — Established News Outlets:
{news_evidence}

### Layer 4 — General Web (context only, DO NOT cite directly):
{web_evidence}

## CONFIDENCE CONTEXT:
- Source confidence score: {confidence:.2f}
- Highest source layer: {highest_layer}
- Total sources found: {total_sources}

## VERDICT LABELS (choose exactly one):
- TRUE: Claim is accurate based on evidence
- FALSE: Claim is demonstrably incorrect
- MISLEADING: Contains true elements but presented in a way that creates false impression
- MOSTLY FALSE: Mostly wrong with minor accurate elements
- OUTDATED: Was true at some point but no longer accurate
- MISSING CONTEXT: True but omits critical information that changes meaning
- OUT OF CONTEXT: Real content used in wrong context (e.g., old photo presented as recent)
- UNVERIFIED: Insufficient evidence to determine truth

## RESPONSE FORMAT (JSON):
{{
    "label": "one of the labels above",
    "confidence": 0.0 to 1.0,
    "summary": "One-sentence verdict (friendly tone, max 100 chars)",
    "explanation": "2-3 sentence explanation with specific source citations",
    "partial_truth_pattern": "if MISLEADING/MOSTLY FALSE/OUTDATED/MISSING CONTEXT/OUT OF CONTEXT, explain what part is true and what part is false/misleading",
    "cited_sources": ["url1", "url2"]
}}"""


async def produce_verdict(claim: str, evidence: SourceEvidence) -> Verdict:
    """Reason over evidence and produce a verdict for a claim."""
    fact_check_text = _format_fact_checks(evidence)
    official_text = _format_official(evidence)
    news_text = _format_news(evidence)
    web_text = _format_web(evidence)

    prompt = VERDICT_PROMPT.format(
        claim=claim,
        fact_check_evidence=fact_check_text or "No fact-check results found.",
        official_evidence=official_text or "No official source results found.",
        news_evidence=news_text or "No news coverage found.",
        web_evidence=web_text or "No general web results found.",
        confidence=evidence.confidence,
        highest_layer=evidence.highest_layer,
        total_sources=evidence.total_sources,
    )

    try:
        response = await _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a fact-checking engine. Respond ONLY with valid JSON. "
                        "Never fabricate sources. If unsure, say UNVERIFIED."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        data = json.loads(content)

        label_str = data.get("label", "UNVERIFIED").upper()
        try:
            label = VerdictLabel(label_str)
        except ValueError:
            label = VerdictLabel.UNVERIFIED

        llm_confidence = float(data.get("confidence", 0.5))
        final_confidence = _calibrate_confidence(llm_confidence, evidence.confidence)

        verdict = Verdict(
            label=label,
            confidence=final_confidence,
            summary=data.get("summary", "Unable to determine verdict."),
            explanation=data.get("explanation", ""),
            sources=evidence.citable_sources()[:5],
            partial_truth_pattern=data.get("partial_truth_pattern", ""),
            claim=claim,
        )

        logger.info(
            "Verdict: claim=%r label=%s confidence=%.2f",
            claim[:60],
            verdict.label.value,
            verdict.confidence,
        )
        return verdict

    except Exception:
        logger.exception("Verdict engine failed for claim: %s", claim[:60])
        return Verdict(
            label=VerdictLabel.UNVERIFIED,
            confidence=0.1,
            summary="Sorry, I couldn't verify this right now.",
            explanation="An error occurred during fact-checking. Please try again.",
            claim=claim,
        )


def _calibrate_confidence(llm_confidence: float, source_confidence: float) -> float:
    """Blend LLM's self-assessed confidence with source-layer confidence.

    Source confidence is weighted higher to prevent overconfident LLM outputs.
    """
    return round(0.4 * llm_confidence + 0.6 * source_confidence, 2)


def _format_fact_checks(evidence: SourceEvidence) -> str:
    lines = []
    for fc in evidence.fact_checks:
        lines.append(
            f"- [{fc.publisher}] Rating: {fc.rating} | Claim: {fc.claim_text} | URL: {fc.url}"
        )
    return "\n".join(lines)


def _format_official(evidence: SourceEvidence) -> str:
    lines = []
    for r in evidence.official_results:
        lines.append(f"- [{r.domain}] {r.title} | URL: {r.url}\n  Content: {r.content[:300]}")
    return "\n".join(lines)


def _format_news(evidence: SourceEvidence) -> str:
    lines = []
    for r in evidence.news_results:
        lines.append(f"- [{r.domain}] {r.title} | URL: {r.url}\n  Content: {r.content[:300]}")
    return "\n".join(lines)


def _format_web(evidence: SourceEvidence) -> str:
    lines = []
    for r in evidence.web_results:
        lines.append(f"- [{r.domain}] {r.title} | URL: {r.url}\n  Content: {r.content[:200]}")
    return "\n".join(lines)
