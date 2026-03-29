"""Format verdicts into WhatsApp-friendly messages.

Verdict-first layout: overall verdict at the top so users see the bottom line
immediately, followed by concise per-claim detail and consolidated sources.
"""

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

_CLEAR_CUT_LABELS = {VerdictLabel.TRUE, VerdictLabel.FALSE}
_NUANCED_LABELS = {
    VerdictLabel.MISLEADING,
    VerdictLabel.MOSTLY_FALSE,
    VerdictLabel.OUTDATED,
    VerdictLabel.MISSING_CONTEXT,
    VerdictLabel.OUT_OF_CONTEXT,
}

HIGH_CONFIDENCE_THRESHOLD = 0.80


def _source_title(src: dict) -> str:
    """Safely extract a display title from a source dict."""
    return str(src.get("title", src.get("domain", "Source")))[:60]


def _source_url(src: dict) -> str:
    """Safely extract URL from a source dict."""
    return str(src.get("url", ""))


def _inline_sources(sources: list[dict], limit: int = 2) -> str:
    """Return a short inline source reference like '(RBI.org, Economic Times)'."""
    names: list[str] = []
    for src in sources[:limit]:
        name = src.get("domain", "") or src.get("title", "")
        if name:
            names.append(str(name).split("/")[0][:25])
    return f"({', '.join(names)})" if names else ""


def _is_clear_cut(verdict: Verdict) -> bool:
    """A verdict is clear-cut when the label is TRUE/FALSE with high confidence."""
    return (
        verdict.label in _CLEAR_CUT_LABELS
        and verdict.confidence >= HIGH_CONFIDENCE_THRESHOLD
    )


def _overall_emoji(verdicts: list[Verdict]) -> str:
    """Pick the dominant emoji for the overall verdict header."""
    false_count = sum(
        1 for v in verdicts
        if v.label in (VerdictLabel.FALSE, VerdictLabel.MOSTLY_FALSE)
    )
    true_count = sum(1 for v in verdicts if v.label == VerdictLabel.TRUE)
    misleading_count = sum(1 for v in verdicts if v.label in _NUANCED_LABELS)
    total = len(verdicts)

    if false_count == total:
        return "❌"
    if true_count == total:
        return "✅"
    if false_count > total / 2:
        return "🔴"
    if misleading_count > total / 2:
        return "⚠️"
    if true_count > total / 2:
        return "✅"
    return "⚠️"


def _overall_label(verdicts: list[Verdict]) -> str:
    """Generate a human-readable overall verdict label."""
    false_count = sum(
        1 for v in verdicts
        if v.label in (VerdictLabel.FALSE, VerdictLabel.MOSTLY_FALSE)
    )
    true_count = sum(1 for v in verdicts if v.label == VerdictLabel.TRUE)
    total = len(verdicts)

    if false_count == total:
        return "False"
    if true_count == total:
        return "True"
    if false_count > total / 2:
        return "Mostly False"
    if true_count > total / 2:
        return "Mostly True"
    return "Mixed Results"


def _overall_summary(verdicts: list[Verdict]) -> str:
    """Build a 1-2 sentence synthesis of all verdicts."""
    false_labels = {VerdictLabel.FALSE, VerdictLabel.MOSTLY_FALSE}
    false_count = sum(1 for v in verdicts if v.label in false_labels)
    true_count = sum(1 for v in verdicts if v.label == VerdictLabel.TRUE)
    nuanced_count = sum(1 for v in verdicts if v.label in _NUANCED_LABELS)
    total = len(verdicts)

    if false_count == total:
        return f"None of the {total} claims in this message are supported by evidence."
    if true_count == total:
        return f"All {total} claims in this message are supported by evidence."

    segments: list[str] = []
    segments.append(f"This message contains {total} claims")
    detail_parts: list[str] = []
    if true_count:
        detail_parts.append(f"{true_count} supported")
    if false_count:
        detail_parts.append(f"{false_count} not supported")
    if nuanced_count:
        detail_parts.append(f"{nuanced_count} misleading or lacking context")
    if detail_parts:
        segments.append(" — " + ", ".join(detail_parts) + " by evidence.")
    else:
        segments.append(".")
    return "".join(segments)


def _confidence_tip(verdicts: list[Verdict]) -> str:
    """Return a tip if any verdict has low/medium confidence."""
    any_low = any(confidence_tier(v.confidence) == "low" for v in verdicts)
    any_medium = any(confidence_tier(v.confidence) == "medium" for v in verdicts)
    if any_low:
        return "💡 _Some claims had limited sources — verify before sharing._"
    if any_medium:
        return "💡 _Check the sources below before sharing._"
    return ""


def _collect_sources(verdicts: list[Verdict], limit: int = 5) -> list[dict]:
    """De-duplicate and collect sources across all verdicts."""
    all_sources: list[dict] = []
    seen_urls: set[str] = set()
    for v in verdicts:
        for src in v.sources:
            url = _source_url(src)
            if url and url not in seen_urls:
                all_sources.append(src)
                seen_urls.add(url)
    return all_sources[:limit]


def _format_sources_block(sources: list[dict]) -> list[str]:
    """Render the consolidated sources block."""
    if not sources:
        return []
    lines = ["📎 *Sources:*"]
    for i, src in enumerate(sources[:5], 1):
        lines.append(f"{i}. {_source_title(src)}")
        url = _source_url(src)
        if url:
            lines.append(f"   {url}")
    return lines


def format_verdict(verdict: Verdict) -> str:
    """Format a single verdict into a WhatsApp message (verdict-first)."""
    emoji = VERDICT_EMOJI.get(verdict.label, "❓")

    parts = [
        f"{emoji} *Verdict: {verdict.label.value}*",
        verdict.summary,
    ]

    if verdict.explanation:
        parts.extend(["", verdict.explanation])

    if verdict.partial_truth_pattern:
        parts.extend(["", f"📋 *What's true vs. what's not:*", verdict.partial_truth_pattern])

    tip = _confidence_tip([verdict])
    if tip:
        parts.extend(["", tip])

    source_lines = _format_sources_block(verdict.sources[:3])
    if source_lines:
        parts.extend(["", *source_lines])

    return "\n".join(parts)


def format_multi_verdict(verdicts: list[Verdict]) -> str:
    """Format multiple verdicts with the overall verdict at the top."""
    if len(verdicts) == 1:
        return format_verdict(verdicts[0])

    emoji = _overall_emoji(verdicts)
    label = _overall_label(verdicts)
    summary = _overall_summary(verdicts)

    parts = [
        f"{emoji} *Verdict: {label}*",
        summary,
        "",
        "---",
        "",
    ]

    for i, v in enumerate(verdicts, 1):
        v_emoji = VERDICT_EMOJI.get(v.label, "❓")
        src_ref = _inline_sources(v.sources)

        parts.append(f"*Claim {i}:* _{v.claim}_")

        if _is_clear_cut(v):
            line = f"{v_emoji} *{v.label.value}* — {v.summary}"
            if src_ref:
                line += f" {src_ref}"
            parts.append(line)
        else:
            parts.append(f"{v_emoji} *{v.label.value}* — {v.summary}")
            if v.explanation:
                parts.append(v.explanation)
            if v.partial_truth_pattern:
                parts.append(f"↳ {v.partial_truth_pattern[:250]}")
            if src_ref:
                parts.append(f"_{src_ref}_")

        parts.append("")

    tip = _confidence_tip(verdicts)
    if tip:
        parts.append(tip)
        parts.append("")

    all_sources = _collect_sources(verdicts)
    source_lines = _format_sources_block(all_sources)
    if source_lines:
        parts.extend(source_lines)

    return "\n".join(parts)
