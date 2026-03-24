"""Confidence scoring and verdict label assignment."""

from __future__ import annotations

from enum import Enum


class VerdictLabel(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    MISLEADING = "MISLEADING"
    MOSTLY_FALSE = "MOSTLY FALSE"
    OUTDATED = "OUTDATED"
    MISSING_CONTEXT = "MISSING CONTEXT"
    OUT_OF_CONTEXT = "OUT OF CONTEXT"
    UNVERIFIED = "UNVERIFIED"
    AI_GENERATED = "AI-GENERATED"


# Confidence thresholds
HIGH_CONFIDENCE = 0.80
MEDIUM_CONFIDENCE = 0.50


def confidence_tier(score: float) -> str:
    """Return the confidence tier for display."""
    if score >= HIGH_CONFIDENCE:
        return "high"
    if score >= MEDIUM_CONFIDENCE:
        return "medium"
    return "low"
