from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response

from app.config import LOG_LEVEL
from app.whatsapp.webhook import router as whatsapp_router
from app.db.database import init_db

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


app.include_router(whatsapp_router, prefix="/webhook")
