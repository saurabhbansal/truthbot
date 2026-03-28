"""Hash-based caching for fact-check results and evidence to avoid redundant API calls."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from app.db.database import get_db
from app.utils.logger import get_logger

logger = get_logger("db.cache")

CACHE_TTL_HOURS = 24


def content_hash(content: str) -> str:
    """Generate a deterministic hash for content deduplication."""
    normalized = content.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


async def get_cached_verdict(content: str) -> dict | None:
    """Check if we have a cached verdict for this content."""
    h = content_hash(content)
    try:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT verdict_json, created_at FROM cache WHERE content_hash = ?",
                (h,),
            )
            row = await cursor.fetchone()

            if not row:
                return None

            created_at = datetime.fromisoformat(row[1])
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - created_at > timedelta(hours=CACHE_TTL_HOURS):
                await db.execute("DELETE FROM cache WHERE content_hash = ?", (h,))
                await db.commit()
                logger.info("Cache expired for hash %s", h[:12])
                return None

            logger.info("Cache hit for hash %s", h[:12])
            return json.loads(row[0])
        finally:
            await db.close()

    except Exception:
        logger.exception("Cache lookup failed")
        return None


async def set_cached_verdict(content: str, verdict_data: dict) -> None:
    """Store a verdict in the cache."""
    h = content_hash(content)
    try:
        db = await get_db()
        try:
            await db.execute(
                "INSERT OR REPLACE INTO cache (content_hash, verdict_json) VALUES (?, ?)",
                (h, json.dumps(verdict_data)),
            )
            await db.commit()
            logger.info("Cached verdict for hash %s", h[:12])
        finally:
            await db.close()
    except Exception:
        logger.exception("Cache write failed")


async def get_cached_evidence(claim: str) -> "SourceEvidence | None":
    """Check if we have cached evidence for this claim."""
    h = content_hash(claim)
    try:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT evidence_json, created_at FROM evidence_cache WHERE claim_hash = ?",
                (h,),
            )
            row = await cursor.fetchone()

            if not row:
                return None

            created_at = datetime.fromisoformat(row[1])
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - created_at > timedelta(hours=CACHE_TTL_HOURS):
                await db.execute("DELETE FROM evidence_cache WHERE claim_hash = ?", (h,))
                await db.commit()
                return None

            logger.info("Evidence cache hit for claim hash %s", h[:12])
            return _deserialize_evidence(claim, json.loads(row[0]))
        finally:
            await db.close()

    except Exception:
        logger.exception("Evidence cache lookup failed")
        return None


async def set_cached_evidence(claim: str, evidence: "SourceEvidence") -> None:
    """Store evidence in the cache."""
    h = content_hash(claim)
    try:
        db = await get_db()
        try:
            await db.execute(
                "INSERT OR REPLACE INTO evidence_cache (claim_hash, evidence_json) VALUES (?, ?)",
                (h, json.dumps(_serialize_evidence(evidence))),
            )
            await db.commit()
            logger.info("Cached evidence for claim hash %s", h[:12])
        finally:
            await db.close()
    except Exception:
        logger.exception("Evidence cache write failed")


async def sweep_expired_cache() -> int:
    """Remove expired entries from all cache tables. Returns count of deleted rows."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
    total = 0
    try:
        db = await get_db()
        try:
            for table in ("cache", "evidence_cache"):
                cursor = await db.execute(
                    f"DELETE FROM {table} WHERE created_at < ?", (cutoff,)
                )
                total += cursor.rowcount
            await db.commit()
            if total:
                logger.info("Cache sweep: removed %d expired entries", total)
        finally:
            await db.close()
    except Exception:
        logger.exception("Cache sweep failed")
    return total


def _serialize_evidence(evidence: "SourceEvidence") -> dict:
    """Serialize SourceEvidence to a JSON-compatible dict."""
    from dataclasses import asdict
    return {
        "fact_checks": [asdict(fc) for fc in evidence.fact_checks],
        "official_results": [asdict(o) for o in evidence.official_results],
        "news_results": [asdict(n) for n in evidence.news_results],
        "web_results": [asdict(w) for w in evidence.web_results],
        "confidence": evidence.confidence,
        "highest_layer": evidence.highest_layer,
    }


def _deserialize_evidence(claim: str, data: dict) -> "SourceEvidence":
    """Deserialize a dict back into SourceEvidence."""
    from app.sources.source_trust import SourceEvidence
    from app.sources.fact_check_db import FactCheckResult
    from app.sources.official_sources import OfficialSourceResult
    from app.sources.news_sources import NewsSourceResult
    from app.sources.web_search import WebSearchResult

    evidence = SourceEvidence(claim=claim)
    evidence.fact_checks = [FactCheckResult(**fc) for fc in data.get("fact_checks", [])]
    evidence.official_results = [OfficialSourceResult(**o) for o in data.get("official_results", [])]
    evidence.news_results = [NewsSourceResult(**n) for n in data.get("news_results", [])]
    evidence.web_results = [WebSearchResult(**w) for w in data.get("web_results", [])]
    evidence.confidence = data.get("confidence", 0.0)
    evidence.highest_layer = data.get("highest_layer", "none")
    return evidence
