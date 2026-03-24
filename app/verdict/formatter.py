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

LOW_CONFIDENCE_TIP = (
    "\n\n💡 _I found limited sources on this, so take this with a pinch of salt. "
    "If you have more context, send it and I'll re-check!_"
)

MEDIUM_CONFIDENCE_TIP = (
    "\n\n💡 _I found some sources but not as many as I'd like. "
    "Check the sources below before sharing._"
)


def _confidence_tip(verdict: Verdict) -> str:
    """Return a contextual tip based on confidence level, or empty string for high confidence."""
    tier = confidence_tier(verdict.confidence)
    if tier == "low":
        return LOW_CONFIDENCE_TIP
    if tier == "medium":
        return MEDIUM_CONFIDENCE_TIP
    return ""


def format_verdict(verdict: Verdict) -> str:
    """Format a single verdict into a WhatsApp message."""
    emoji = VERDICT_EMOJI.get(verdict.label, "❓")

    parts = [
        f"{emoji} *{verdict.label.value}*",
        "",
        verdict.summary,
    ]

    if verdict.explanation:
        parts.extend(["", verdict.explanation])

    if verdict.partial_truth_pattern:
        parts.extend([
            "",
            "📋 *What's true vs. what's not:*",
            verdict.partial_truth_pattern,
        ])

    tip = _confidence_tip(verdict)
    if tip:
        parts.append(tip)

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
        parts.append(f"*Claim {i}:* _{v.claim}_")
        parts.append(f"{emoji} *{v.label.value}* — {v.summary}")
        if v.partial_truth_pattern:
            parts.append(f"   ↳ {v.partial_truth_pattern[:120]}")
        parts.append("")

    any_low = any(confidence_tier(v.confidence) == "low" for v in verdicts)
    any_medium = any(confidence_tier(v.confidence) == "medium" for v in verdicts)
    if any_low:
        parts.append(
            "💡 _Some of these had limited sources — check the links below before sharing._"
        )
        parts.append("")
    elif any_medium:
        parts.append(
            "💡 _Check the sources below before sharing._"
        )
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
