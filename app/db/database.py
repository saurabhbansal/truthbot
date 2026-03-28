from __future__ import annotations

import aiosqlite

from app.config import DATABASE_PATH
from app.utils.logger import get_logger

logger = get_logger("db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    content_hash TEXT PRIMARY KEY,
    verdict_json TEXT NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evidence_cache (
    claim_hash    TEXT PRIMARY KEY,
    evidence_json TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    verdict_id          TEXT NOT NULL,
    user_phone_hash     TEXT NOT NULL,
    feedback_type       TEXT NOT NULL,
    negative_reason     TEXT,
    source_link         TEXT,
    source_quality      REAL,
    free_text           TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usage_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_phone_hash TEXT NOT NULL,
    message_type    TEXT NOT NULL,
    verdict_label   TEXT,
    confidence      REAL,
    processing_ms   INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_usage (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_phone_hash TEXT NOT NULL,
    message_type    TEXT NOT NULL,
    date            TEXT NOT NULL DEFAULT (date('now')),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cache_created ON cache(created_at);
CREATE INDEX IF NOT EXISTS idx_evidence_cache_created ON evidence_cache(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_verdict ON feedback(verdict_id);
CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_stats(user_phone_hash);
CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_stats(created_at);
CREATE INDEX IF NOT EXISTS idx_daily_usage_user_date ON daily_usage(user_phone_hash, date);
CREATE INDEX IF NOT EXISTS idx_daily_usage_date ON daily_usage(date);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
    logger.info("Database initialized at %s", DATABASE_PATH)


async def get_db() -> aiosqlite.Connection:
    return await aiosqlite.connect(DATABASE_PATH)
