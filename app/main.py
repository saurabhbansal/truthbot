from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.config import LOG_LEVEL
from app.db.cache import sweep_expired_cache
from app.db.database import init_db
from app.db.usage import get_message_type_trend, get_stats, sweep_retention_data
from app.feedback.feedback_handler import get_feedback_stats
from app.whatsapp.webhook import router as whatsapp_router

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("truthbot")

app = FastAPI(title="TruthBot", version="0.1.0")


async def _periodic_maintenance() -> None:
    """Run periodic cache and retention maintenance."""
    while True:
        await asyncio.sleep(6 * 3600)
        try:
            await sweep_expired_cache()
            await sweep_retention_data()
        except Exception:
            logger.exception("Periodic maintenance error")


@app.on_event("startup")
async def startup() -> None:
    await init_db()
    asyncio.create_task(_periodic_maintenance())
    logger.info("TruthBot started")


@app.get("/")
async def health() -> dict:
    return {"status": "ok", "service": "TruthBot", "version": "0.1.0"}


@app.get("/stats")
async def stats() -> dict:
    return await get_stats()


@app.get("/feedback-stats")
async def feedback_stats(days: int = 30) -> dict:
    feedback = await get_feedback_stats(days=days)
    trend = await get_message_type_trend(days=days)
    feedback["message_type_trend"] = trend
    return feedback


@app.get("/admin/feedback", response_class=HTMLResponse)
async def feedback_dashboard(days: int = 30) -> str:
    data = await get_feedback_stats(days=days)
    usage = await get_stats()
    reasons = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>"
        for k, v in data.get("negative_reasons", {}).items()
    ) or "<tr><td colspan='2'>No negative reasons yet</td></tr>"
    trend_rows = "".join(
        f"<tr><td>{row['date']}</td><td>{row['count']}</td></tr>"
        for row in data.get("trend", [])
    ) or "<tr><td colspan='2'>No feedback trend data yet</td></tr>"
    by_type_rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>"
        for k, v in usage.get("by_type", {}).items()
    ) or "<tr><td colspan='2'>No message type data yet</td></tr>"

    return f"""
    <html>
      <head><title>TruthBot Feedback Dashboard</title></head>
      <body style="font-family: Arial, sans-serif; max-width: 1000px; margin: 24px auto; line-height: 1.6;">
        <h1>TruthBot Feedback Dashboard</h1>
        <p><strong>Window:</strong> last {days} days</p>
        <ul>
          <li>Total feedback: {data.get('total_feedback', 0)}</li>
          <li>Positive: {data.get('positive', 0)}</li>
          <li>Negative: {data.get('negative', 0)}</li>
          <li>Positive rate: {data.get('positive_rate_pct', 0.0)}%</li>
        </ul>
        <h2>Negative Reason Breakdown</h2>
        <table border="1" cellpadding="8" cellspacing="0">
          <tr><th>Reason</th><th>Count</th></tr>
          {reasons}
        </table>
        <h2>Feedback Trend</h2>
        <table border="1" cellpadding="8" cellspacing="0">
          <tr><th>Date</th><th>Count</th></tr>
          {trend_rows}
        </table>
        <h2>Checks By Message Type</h2>
        <table border="1" cellpadding="8" cellspacing="0">
          <tr><th>Message Type</th><th>Count</th></tr>
          {by_type_rows}
        </table>
      </body>
    </html>
    """


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
        <p>TruthBot may use Meta WhatsApp Cloud API, OpenAI, Google Gemini, Tavily, Google APIs, and cloud hosting providers to deliver functionality.</p>
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
