from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

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


@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy() -> str:
    return """
    <html>
      <head><title>TruthBot Privacy Policy</title></head>
      <body style="font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; line-height: 1.6;">
        <h1>TruthBot Privacy Policy</h1>
        <p><strong>Last updated:</strong> 2026-03-24</p>
        <p>TruthBot is a WhatsApp-based fact-checking assistant. We process message content and media that users send to provide fact-checking responses.</p>
        <h2>Data We Process</h2>
        <ul>
          <li>Messages, links, captions, and media you submit for analysis</li>
          <li>Operational metadata needed for routing and response delivery</li>
          <li>Feedback and usage metrics for quality improvement</li>
        </ul>
        <h2>Why We Process Data</h2>
        <ul>
          <li>To provide fact-checking results and source-backed responses</li>
          <li>To improve reliability, quality, and safety</li>
          <li>To debug failures and monitor abuse/rate limits</li>
        </ul>
        <h2>Third-Party Services</h2>
        <p>TruthBot may use Meta WhatsApp Cloud API, OpenAI, Tavily, Google APIs, Hive, and cloud hosting providers to deliver functionality.</p>
        <h2>Contact</h2>
        <p>Email: <a href="mailto:factfuryteam@gmail.com">factfuryteam@gmail.com</a></p>
        <h2>Data Deletion</h2>
        <p>See <a href="/data-deletion">Data Deletion Instructions</a>.</p>
      </body>
    </html>
    """


@app.get("/terms", response_class=HTMLResponse)
async def terms() -> str:
    return """
    <html>
      <head><title>TruthBot Terms of Service</title></head>
      <body style="font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; line-height: 1.6;">
        <h1>TruthBot Terms of Service</h1>
        <p><strong>Last updated:</strong> 2026-03-24</p>
        <p>TruthBot provides best-effort fact-checking and is for informational purposes only. It is not legal, medical, or financial advice.</p>
        <p>Users must not abuse the service or submit unlawful content.</p>
        <p>Contact: <a href="mailto:factfuryteam@gmail.com">factfuryteam@gmail.com</a></p>
      </body>
    </html>
    """


@app.get("/data-deletion", response_class=HTMLResponse)
async def data_deletion() -> str:
    return """
    <html>
      <head><title>TruthBot Data Deletion Instructions</title></head>
      <body style="font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; line-height: 1.6;">
        <h1>TruthBot Data Deletion Instructions</h1>
        <p>Email <a href="mailto:factfuryteam@gmail.com">factfuryteam@gmail.com</a> with subject
        <strong>TruthBot data deletion request</strong> and include your WhatsApp number in international format.</p>
        <p>We target completion within 7 business days.</p>
      </body>
    </html>
    """


app.include_router(whatsapp_router, prefix="/webhook")
