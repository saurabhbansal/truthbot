"""Format verdicts into WhatsApp-friendly messages."""

from __future__ import annotations

from app.engines.verdict_engine import Verdict
from app.verdict.confidence import VerdictLabel, confidence_tier

VERDICT_EMOJI = {
    VerdictLabel.TRUE: "✅",
    VerdictLabel.FALSE: "❌",
    VerdictLabel.MISLEADING: "⚠️",
    VerdictLabel.MOSTLY_FALSE: "🔴",
    VerdictLabel.OUTDATED: "🕐",
    VerdictLabel.MISSING_CONTEXT: "🔍",
    VerdictLabel.OUT_OF_CONTEXT: "🔄",
    VerdictLabel.UNVERIFIED: "❓",
    VerdictLabel.AI_GENERATED: "🤖",
}

CONFIDENCE_EMOJI = {
    "high": "🟢",
    "medium": "🟡",
    "low": "🔴",
}

CONFIDENCE_TEXT = {
    "high": "High confidence",
    "medium": "Medium confidence — take with a pinch of salt",
    "low": "Low confidence — limited sources available",
}


def format_verdict(verdict: Verdict) -> str:
    """Format a single verdict into a WhatsApp message."""
    emoji = VERDICT_EMOJI.get(verdict.label, "❓")
    tier = confidence_tier(verdict.confidence)
    conf_emoji = CONFIDENCE_EMOJI.get(tier, "🔴")
    conf_text = CONFIDENCE_TEXT.get(tier, "")

    parts = [
        f"{emoji} *{verdict.label.value}*",
        "",
        verdict.summary,
        "",
        f"{conf_emoji} _{conf_text}_",
    ]

    if verdict.explanation:
        parts.extend(["", verdict.explanation])

    if verdict.partial_truth_pattern:
        parts.extend([
            "",
            "📋 *What's true vs. what's not:*",
            verdict.partial_truth_pattern,
        ])

    if verdict.sources:
        parts.append("")
        parts.append("📎 *Sources:*")
        for i, src in enumerate(verdict.sources[:3], 1):
            parts.append(f"{i}. {src['title'][:60]}")
            parts.append(f"   {src['url']}")

    return "\n".join(parts)


def format_multi_verdict(verdicts: list[Verdict]) -> str:
    """Format multiple verdicts (for messages with multiple claims)."""
    if len(verdicts) == 1:
        return format_verdict(verdicts[0])

    parts = ["🔎 *TruthBot found multiple claims to check:*", ""]

    for i, v in enumerate(verdicts, 1):
        emoji = VERDICT_EMOJI.get(v.label, "❓")
        parts.append(f"*Claim {i}:* _{v.claim[:80]}_")
        parts.append(f"{emoji} *{v.label.value}* — {v.summary}")
        if v.partial_truth_pattern:
            parts.append(f"   ↳ {v.partial_truth_pattern[:120]}")
        parts.append("")

    all_sources = []
    seen_urls: set[str] = set()
    for v in verdicts:
        for src in v.sources:
            if src["url"] not in seen_urls:
                all_sources.append(src)
                seen_urls.add(src["url"])

    if all_sources:
        parts.append("📎 *Sources:*")
        for i, src in enumerate(all_sources[:5], 1):
            parts.append(f"{i}. {src['title'][:60]}")
            parts.append(f"   {src['url']}")

    return "\n".join(parts)
