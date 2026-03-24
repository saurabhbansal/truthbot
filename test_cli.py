"""Interactive CLI test harness for TruthBot.

Simulates WhatsApp message flow locally so you can test all engines
without needing a phone number or webhook.

Usage:
    python test_cli.py

Commands:
    text <message>     - Fact-check a text claim
    link <url>         - Fact-check a link
    image <path>       - Analyze a local image file
    video <path>       - Analyze a local video file
    help               - Show TruthBot help message
    hi                 - Show onboarding message
    stats              - Show usage statistics
    quit               - Exit
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from app.db.database import init_db
from app.engines.text_handler import fact_check_text
from app.engines.link_handler import fact_check_link, classify_url
from app.engines.image_handler import fact_check_image
from app.engines.video_handler import fact_check_video
from app.db.usage import get_stats, log_usage

BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

ONBOARDING = """
Hey there! I'm TruthBot 🔍

I help you check if messages, images, links, and videos are real or fake.

HOW TO USE ME:
Just forward me anything you want checked! That's it.

I can check:
• Text messages & chain forwards
• News links & articles
• Images & screenshots
• Videos (AI-generated & deepfakes)

Try it now — forward me something from your groups!
"""

HELP = """
Here's how I can help:

FORWARD me any:
• Text message or chain forward
• Image or screenshot
• News link or article URL
• Video clip

And I'll tell you if it's real, fake, or misleading.

TIPS:
• The more context, the better — forward the full message
• I work best with specific claims
• I'll always tell you when I'm not sure
"""


def print_bot(text: str) -> None:
    print(f"\n{GREEN}{BOLD}TruthBot:{RESET}")
    for line in text.split("\n"):
        print(f"  {GREEN}{line}{RESET}")
    print()


def print_info(text: str) -> None:
    print(f"  {YELLOW}{text}{RESET}")


def print_error(text: str) -> None:
    print(f"  {RED}{text}{RESET}")


async def handle_text(text: str) -> None:
    print_info("Checking claims... (this takes 5-15 seconds)")
    start = time.time()
    message, verdicts = await fact_check_text(text)
    elapsed = time.time() - start
    print_bot(message)
    print_info(f"[{elapsed:.1f}s | {len(verdicts)} verdict(s)]")
    await log_usage("cli_test", "text", verdicts[0].label.value if verdicts else "", 0, int(elapsed * 1000))


async def handle_link(url: str) -> None:
    print_info("Analyzing article... (this takes 10-20 seconds)")
    start = time.time()
    message = await fact_check_link(url)
    elapsed = time.time() - start
    print_bot(message)
    print_info(f"[{elapsed:.1f}s]")
    await log_usage("cli_test", "link", "", 0, int(elapsed * 1000))


async def handle_image(path: str) -> None:
    file_path = Path(path)
    if not file_path.exists():
        print_error(f"File not found: {path}")
        return
    print_info(f"Analyzing image: {file_path.name} ({file_path.stat().st_size / 1024:.0f} KB)")
    print_info("Running OCR + AI detection... (this takes 10-20 seconds)")
    start = time.time()
    image_bytes = file_path.read_bytes()
    message = await fact_check_image(image_bytes)
    elapsed = time.time() - start
    print_bot(message)
    print_info(f"[{elapsed:.1f}s]")
    await log_usage("cli_test", "image", "", 0, int(elapsed * 1000))


async def handle_video(path: str) -> None:
    file_path = Path(path)
    if not file_path.exists():
        print_error(f"File not found: {path}")
        return
    size_mb = file_path.stat().st_size / (1024 * 1024)
    print_info(f"Analyzing video: {file_path.name} ({size_mb:.1f} MB)")
    if size_mb > 20:
        print_error("Video too large (max 20MB)")
        return
    print_info("Running deepfake detection... (this takes 30-60 seconds)")
    start = time.time()
    video_bytes = file_path.read_bytes()
    message = await fact_check_video(video_bytes)
    elapsed = time.time() - start
    print_bot(message)
    print_info(f"[{elapsed:.1f}s]")
    await log_usage("cli_test", "video", "", 0, int(elapsed * 1000))


async def handle_stats() -> None:
    stats = await get_stats()
    print_bot(
        f"Total checks: {stats.get('total_checks', 0)}\n"
        f"Unique users: {stats.get('unique_users', 0)}\n"
        f"By type: {stats.get('by_type', {})}\n"
        f"By verdict: {stats.get('by_verdict', {})}"
    )


async def main() -> None:
    await init_db()

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  TruthBot CLI Test Harness{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"""
  Commands:
    {BLUE}text{RESET} <message>     Fact-check a text claim
    {BLUE}link{RESET} <url>         Fact-check a link
    {BLUE}image{RESET} <path>       Analyze a local image file
    {BLUE}video{RESET} <path>       Analyze a local video file
    {BLUE}hi{RESET}                 Show onboarding message
    {BLUE}help{RESET}               Show help message
    {BLUE}stats{RESET}              Show usage statistics
    {BLUE}quit{RESET}               Exit
    """)

    while True:
        try:
            raw = input(f"{BLUE}{BOLD}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not raw:
            continue

        lower = raw.lower()

        if lower in ("quit", "exit", "q"):
            print("Bye!")
            break
        elif lower in ("hi", "hello", "hey", "namaste", "start"):
            print_bot(ONBOARDING)
        elif lower in ("help", "menu", "?"):
            print_bot(HELP)
        elif lower == "stats":
            await handle_stats()
        elif lower.startswith("text "):
            await handle_text(raw[5:].strip())
        elif lower.startswith("link "):
            await handle_link(raw[5:].strip())
        elif lower.startswith("image "):
            await handle_image(raw[6:].strip())
        elif lower.startswith("video "):
            await handle_video(raw[6:].strip())
        else:
            # Treat bare input as text fact-check
            await handle_text(raw)


if __name__ == "__main__":
    asyncio.run(main())
