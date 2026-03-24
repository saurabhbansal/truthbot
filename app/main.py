from __future__ import annotations

import logging

from fastapi import FastAPI

from app.config import LOG_LEVEL
from app.db.database import init_db
from app.db.usage import get_stats
from app.whatsapp.webhook import router as whatsapp_router

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("truthbot")

app = FastAPI(title="TruthBot", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    await init_db()
    logger.info("TruthBot started")


@app.get("/")
async def health() -> dict:
    return {"status": "ok", "service": "TruthBot", "version": "0.1.0"}


@app.get("/stats")
async def stats() -> dict:
    return await get_stats()


app.include_router(whatsapp_router, prefix="/webhook")
