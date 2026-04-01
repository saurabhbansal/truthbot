from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("WHATSAPP_ACCESS_TOKEN", "local")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "local")
os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", "local")
os.environ.setdefault("OPENAI_API_KEY", "local")
os.environ.setdefault("GEMINI_API_KEY", "local")
os.environ.setdefault("TAVILY_API_KEY", "local")
os.environ.setdefault("GOOGLE_API_KEY", "local")


def _assert(condition: bool, msg: str) -> None:
    if not condition:
        raise AssertionError(msg)


async def run_text_smoke() -> None:
    from app.engines import claim_extractor

    # Simulate Gemini returning non-strict payload.
    fake_response = SimpleNamespace(
        text='claims -> "Traffic is 104 hrs/year in Delhi" and "Traffic is 168 hrs/year in Bengaluru"'
    )
    with patch.object(
        claim_extractor.gemini_client.models,
        "generate_content",
        return_value=fake_response,
    ):
        claims = await claim_extractor.extract_claims("dummy text")
        _assert(len(claims) >= 2, f"text smoke expected >=2 claims, got {claims}")


async def run_image_smoke() -> None:
    from app.engines import image_handler

    fake_fact_check = AsyncMock(return_value=("✅ Verdict test output", []))
    with patch.object(
        image_handler, "_analyze_image_with_openai", AsyncMock(return_value="Claim: Delhi traffic is 104 hours/year")
    ), patch.object(
        image_handler, "extract_text_from_image", AsyncMock(return_value="Delhi traffic is 104 hours/year")
    ), patch.object(
        image_handler, "fact_check_text", fake_fact_check
    ):
        out = await image_handler.fact_check_image(b"\x89PNGdummy", caption="")
        _assert("Verdict test output" in out, "image smoke expected verdict output text")


async def run_link_smoke() -> None:
    from app.engines import link_handler

    fake_fact_check = AsyncMock(return_value=("✅ Link verdict output", [object()]))
    with patch.object(link_handler, "_ytdlp_metadata", AsyncMock(return_value={"title": "Test title"})), patch.object(
        link_handler, "_ytdlp_subtitles", AsyncMock(return_value="")
    ), patch.object(
        link_handler, "_search_about_video", AsyncMock(return_value="- context")
    ), patch.object(
        link_handler, "_download_and_analyze_video", AsyncMock(return_value=None)
    ), patch.object(
        link_handler, "fact_check_text", fake_fact_check
    ):
        out = await link_handler.fact_check_link("https://instagram.com/reel/abc")
        _assert("Link verdict output" in out, "link smoke expected verdict output")


async def main() -> int:
    import asyncio

    await run_text_smoke()
    await run_image_smoke()
    await run_link_smoke()
    print("Local offline smoke passed: text/image/video-link paths.")
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
