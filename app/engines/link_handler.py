"""Link fact-check handler -- extract article content, check domain credibility, fact-check claims.

Video links use a 4-tier hybrid pipeline:
  Tier 1: yt-dlp metadata (no download)
  Tier 2: Transcript extraction (youtube-transcript-api / yt-dlp subtitles)
  Tier 3: Web search for existing fact-checks
  Tier 4: Full download via yt-dlp + ffmpeg/Vision/Whisper analysis
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from urllib.parse import urlparse, parse_qs

from tavily import AsyncTavilyClient

from app.config import (
    MAX_VIDEO_DOWNLOAD_SIZE,
    TAVILY_API_KEY,
    VIDEO_DOWNLOAD_TIMEOUT,
)
from app.engines.text_handler import fact_check_text
from app.engines.video_handler import analyze_video_file
from app.sources.allowlists import (
    ALL_NEWS_DOMAINS,
    ALL_OFFICIAL_DOMAINS,
    BLOCKED_DOMAINS,
    FACT_CHECKERS,
)
from app.utils.logger import get_logger

logger = get_logger("engines.link")

URL_PATTERN = re.compile(r"https?://[^\s<>\"'\)]+")

SOCIAL_DOMAINS = {
    "facebook.com",
    "m.facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "tiktok.com",
}

VIDEO_DOMAINS = {
    "youtube.com",
    "m.youtube.com",
    "youtu.be",
    "instagram.com",
    "tiktok.com",
    "vm.tiktok.com",
    "vimeo.com",
    "dailymotion.com",
    "rumble.com",
    "bitchute.com",
    "odysee.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "m.facebook.com",
    "fb.watch",
    "snapchat.com",
    "story.snapchat.com",
    "twitch.tv",
    "streamable.com",
    "v.redd.it",
    "reddit.com",
}

_VIDEO_PATH_PATTERNS = (
    re.compile(r"/reel/", re.IGNORECASE),
    re.compile(r"/reels/", re.IGNORECASE),
    re.compile(r"/video/", re.IGNORECASE),
    re.compile(r"/videos/", re.IGNORECASE),
    re.compile(r"/shorts/", re.IGNORECASE),
    re.compile(r"/watch", re.IGNORECASE),
    re.compile(r"/p/[A-Za-z0-9_-]+", re.IGNORECASE),
    re.compile(r"/status/\d+", re.IGNORECASE),
    re.compile(r"/clip/", re.IGNORECASE),
)

_MIN_TRANSCRIPT_LENGTH = 100


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text."""
    return URL_PATTERN.findall(text)


def classify_url(url: str) -> dict:
    """Classify a URL by domain credibility."""
    domain = _extract_domain(url)
    if not domain:
        return {"domain": url[:40], "tier": "general", "trust": "unknown", "emoji": "🌐"}

    if domain in FACT_CHECKERS or any(fc in domain for fc in FACT_CHECKERS):
        return {"domain": domain, "tier": "fact_checker", "trust": "highest", "emoji": "✅"}

    if domain in ALL_OFFICIAL_DOMAINS:
        return {"domain": domain, "tier": "official", "trust": "high", "emoji": "🏛️"}

    if domain in ALL_NEWS_DOMAINS:
        return {"domain": domain, "tier": "news", "trust": "medium-high", "emoji": "📰"}

    if domain in BLOCKED_DOMAINS:
        return {"domain": domain, "tier": "blocked", "trust": "unreliable", "emoji": "🚫"}

    return {"domain": domain, "tier": "general", "trust": "unknown", "emoji": "🌐"}


_ALWAYS_VIDEO_DOMAINS = {
    "youtube.com", "m.youtube.com", "youtu.be",
    "tiktok.com", "vm.tiktok.com",
    "vimeo.com", "dailymotion.com", "rumble.com", "bitchute.com", "odysee.com",
    "fb.watch", "streamable.com", "v.redd.it", "twitch.tv",
}

_PATH_CHECK_DOMAINS = {
    "instagram.com", "x.com", "twitter.com",
    "facebook.com", "m.facebook.com",
    "snapchat.com", "story.snapchat.com",
    "reddit.com",
}


def is_video_link(url: str) -> bool:
    """Detect whether a URL points to a video."""
    domain = _extract_domain(url)
    if domain in _ALWAYS_VIDEO_DOMAINS:
        return True
    if domain in _PATH_CHECK_DOMAINS:
        for pat in _VIDEO_PATH_PATTERNS:
            if pat.search(url):
                return True
    return False


async def fact_check_link(url: str) -> str:
    """Full link fact-checking pipeline."""
    classification = classify_url(url)
    domain = classification["domain"]

    parts: list[str] = []

    if classification["tier"] == "blocked":
        parts.append(f"🔗 *Link from:* _{domain}_")
        parts.append("")
        parts.append(
            "🚫 *Warning:* This domain is on our blocklist of known unreliable sources. "
            "Content from this site has frequently been found to be inaccurate."
        )
        parts.append("")
        parts.append("💡 _Look for the same story on established news outlets for reliable information._")
        return "\n".join(parts)

    if classification["tier"] == "fact_checker":
        parts.append(f"🔗 *Link from:* _{domain}_")
        parts.append("")
        parts.append(
            "✅ This is a recognized fact-checking organization. "
            "Their verdicts are generally reliable and follow IFCN standards."
        )
        return "\n".join(parts)

    if is_video_link(url):
        return await _handle_video_link(url, domain)

    article_text = await _extract_article(url)

    if not article_text:
        parts.append(f"🔗 *Link from:* _{domain}_")
        parts.append("")
        parts.append(
            "I couldn't extract the article content. "
            "Try copying the key claims from the article and sending them as text!"
        )
        return "\n".join(parts)

    parts.append("📝 *Checking claims from this article:*")
    parts.append("")

    text_message, _ = await fact_check_text(article_text[:3000])
    parts.append(text_message)

    return "\n".join(parts)


async def _handle_video_link(url: str, domain: str) -> str:
    """4-tier hybrid pipeline for video links.

    Tier 1: yt-dlp metadata (no download, free, 2-3s)
    Tier 2: Transcript (youtube-transcript-api or yt-dlp subtitles)
    Tier 3: Web search for existing fact-checks using metadata
    Tier 4: Full download via yt-dlp + ffmpeg/Vision/Whisper pipeline
    """
    # --- Tier 1: Metadata via yt-dlp ---
    meta = await _ytdlp_metadata(url)
    title = meta.get("title", "")
    description = meta.get("description", "")[:1000]
    logger.info("Video meta for %s: title=%r", domain, title[:80] if title else "(none)")

    # --- Tier 2: Transcript ---
    transcript = ""
    if _is_youtube(url):
        transcript = await _get_youtube_transcript(url)
    if not transcript or len(transcript) < _MIN_TRANSCRIPT_LENGTH:
        transcript = await _ytdlp_subtitles(url)

    if transcript and len(transcript) >= _MIN_TRANSCRIPT_LENGTH:
        parts = ["📹 *Checking claims from this video transcript:*", ""]
        text_message, _ = await fact_check_text(transcript[:4000])
        parts.append(text_message)
        return "\n".join(parts)

    # --- Tier 3: Metadata + web search ---
    search_context = await _search_about_video(url, title) if title else ""

    combined_meta = ""
    if title:
        combined_meta = f"Video title: {title}"
    if description:
        combined_meta = f"{combined_meta}\nVideo description: {description}".strip()
    if search_context:
        combined_meta = f"{combined_meta}\n\nWeb context about this video: {search_context}".strip()

    # If we have strong metadata + search results with fact-checks, use them
    if search_context and combined_meta:
        parts = [f"📹 *Checking claims from this video ({domain}):*", ""]
        text_message, _ = await fact_check_text(combined_meta[:4000])
        parts.append(text_message)
        parts.append("")
        parts.append(
            "💡 _Note: I analyzed the video title, description, and web context. "
            "For the most accurate check, you can also type out the specific claim "
            "from the video as text._"
        )
        return "\n".join(parts)

    # --- Tier 4: Full download + analysis ---
    logger.info("Tier 4: attempting full video download for %s", url)
    video_result = await _download_and_analyze_video(url, caption=title)

    if video_result:
        return video_result

    # If we have some metadata but download failed, use what we have
    if combined_meta:
        parts = [f"📹 *Checking claims from this video ({domain}):*", ""]
        text_message, _ = await fact_check_text(combined_meta[:4000])
        parts.append(text_message)
        parts.append("")
        parts.append(
            "💡 _I couldn't download the video directly, so this analysis is based on "
            "the title and description. For a more accurate check, upload the video or "
            "type out the specific claim._"
        )
        return "\n".join(parts)

    # All tiers failed
    return (
        f"📹 *Video link from:* _{domain}_\n\n"
        "I couldn't extract content from this video link.\n\n"
        "You can help me check it in two ways:\n"
        "1️⃣ *Type the claim* — Write out the main claim from the video as text\n"
        "2️⃣ *Upload the video* — Download and send me the video directly, "
        "and I'll analyze the audio and visuals\n\n"
        "💡 _Option 1 is faster and works best for most forwarded videos!_"
    )


# ---------------------------------------------------------------------------
# yt-dlp helpers
# ---------------------------------------------------------------------------

async def _ytdlp_metadata(url: str) -> dict:
    """Extract video metadata via yt-dlp without downloading."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "--dump-json", "--no-download",
            "--no-warnings", "--no-playlist",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            logger.debug("yt-dlp metadata failed: %s", stderr.decode()[:200])
            return {}
        return json.loads(stdout.decode())
    except asyncio.TimeoutError:
        logger.warning("yt-dlp metadata timed out for %s", url)
        return {}
    except Exception:
        logger.debug("yt-dlp metadata error for %s", url)
        return {}


async def _ytdlp_subtitles(url: str) -> str:
    """Try to extract auto-generated subtitles via yt-dlp (no video download)."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_template = os.path.join(tmpdir, "subs")
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "--skip-download",
                "--write-auto-subs",
                "--sub-lang", "en,hi,ta,te,bn,mr,gu,kn,ml,pa,en-orig",
                "--sub-format", "vtt",
                "--convert-subs", "srt",
                "-o", out_template,
                "--no-warnings", "--no-playlist",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)

            # Look for any subtitle file in the temp dir
            for fname in os.listdir(tmpdir):
                if fname.endswith((".srt", ".vtt")):
                    fpath = os.path.join(tmpdir, fname)
                    with open(fpath, encoding="utf-8", errors="ignore") as f:
                        raw = f.read()
                    text = _clean_subtitle_text(raw)
                    if len(text) >= _MIN_TRANSCRIPT_LENGTH:
                        logger.info("yt-dlp subtitles: %d chars from %s", len(text), fname)
                        return text[:5000]
        return ""
    except asyncio.TimeoutError:
        logger.warning("yt-dlp subtitles timed out for %s", url)
        return ""
    except Exception:
        logger.debug("yt-dlp subtitles error for %s", url)
        return ""


def _clean_subtitle_text(raw: str) -> str:
    """Strip SRT/VTT timestamps and formatting, return plain text."""
    lines = raw.splitlines()
    text_lines: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"^\d{2}:\d{2}", line):
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        clean = re.sub(r"<[^>]+>", "", line)
        clean = re.sub(r"\{[^}]+\}", "", clean).strip()
        if clean and clean not in text_lines[-1:]:
            text_lines.append(clean)
    return " ".join(text_lines)


async def _download_and_analyze_video(url: str, caption: str = "") -> str | None:
    """Tier 4: Download video via yt-dlp and run the full analysis pipeline.

    Returns the analysis result string, or None if download fails.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "video.mp4")
            max_size_mb = MAX_VIDEO_DOWNLOAD_SIZE // (1024 * 1024)

            proc = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "-f", "best[filesize<50M]/best",
                "--max-filesize", f"{max_size_mb}M",
                "--merge-output-format", "mp4",
                "-o", out_path,
                "--no-playlist",
                "--no-warnings",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=VIDEO_DOWNLOAD_TIMEOUT
            )

            if proc.returncode != 0:
                logger.info(
                    "yt-dlp download failed (rc=%d): %s",
                    proc.returncode, stderr.decode()[:300],
                )
                return None

            # yt-dlp may add extension variants; find the actual file
            actual_path = out_path
            if not os.path.exists(actual_path):
                for fname in os.listdir(tmpdir):
                    if fname.startswith("video"):
                        actual_path = os.path.join(tmpdir, fname)
                        break

            if not os.path.exists(actual_path):
                logger.warning("yt-dlp produced no output file for %s", url)
                return None

            file_size = os.path.getsize(actual_path)
            if file_size > MAX_VIDEO_DOWNLOAD_SIZE:
                logger.warning("Downloaded video too large: %d bytes", file_size)
                return None

            logger.info("Downloaded video: %d bytes, analyzing...", file_size)
            return await analyze_video_file(actual_path, caption=caption)

    except asyncio.TimeoutError:
        logger.warning("yt-dlp download timed out for %s", url)
        return None
    except Exception:
        logger.exception("Video download+analyze failed for %s", url)
        return None


# ---------------------------------------------------------------------------
# Existing helpers (YouTube transcript, metadata, search)
# ---------------------------------------------------------------------------

def _is_youtube(url: str) -> bool:
    domain = _extract_domain(url)
    return domain in ("youtube.com", "m.youtube.com", "youtu.be")


def _extract_youtube_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")

    if domain == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
        return vid if vid else None

    if domain in ("youtube.com", "m.youtube.com"):
        if "/shorts/" in parsed.path:
            parts = parsed.path.split("/shorts/")
            if len(parts) > 1:
                return parts[1].split("/")[0].split("?")[0]
        qs = parse_qs(parsed.query)
        v = qs.get("v", [None])[0]
        return v

    return None


async def _get_youtube_transcript(url: str) -> str:
    """Try to fetch YouTube transcript using youtube-transcript-api."""
    video_id = _extract_youtube_id(url)
    if not video_id:
        return ""

    try:
        text = await asyncio.to_thread(_fetch_transcript_sync, video_id)
        if text:
            logger.info("YouTube transcript: %d chars for %s", len(text), video_id)
        return text
    except Exception:
        logger.info("No YouTube transcript available for %s", video_id)
        return ""


def _fetch_transcript_sync(video_id: str) -> str:
    """Synchronous YouTube transcript fetch (runs in thread pool)."""
    from youtube_transcript_api import YouTubeTranscriptApi
    ytt = YouTubeTranscriptApi()
    transcript_list = ytt.fetch(video_id)
    text_parts = [entry.text for entry in transcript_list if hasattr(entry, "text")]
    full_text = " ".join(text_parts)
    return full_text[:5000]


async def _search_about_video(url: str, title: str) -> str:
    """Search the web for context about a video using its title."""
    if not title:
        return ""
    try:
        client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
        response = await client.search(
            query=f'fact check: "{title}"',
            search_depth="basic",
            max_results=3,
        )
        results = response.get("results", [])
        snippets = []
        for r in results[:3]:
            content = r.get("content", "")[:300]
            if content:
                snippets.append(f"- {r.get('title', '')}: {content}")
        return "\n".join(snippets)
    except Exception:
        logger.debug("Video context search failed for: %s", title[:60])
        return ""


async def _extract_article(url: str) -> str:
    """Extract article text content using Tavily's extract feature."""
    try:
        client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
        response = await client.extract(urls=[url])

        results = response.get("results", [])
        if results:
            raw_content = results[0].get("raw_content", "")
            return _clean_extracted_content(url, raw_content)[:3000]
        return ""

    except Exception:
        logger.exception("Article extraction failed for: %s", url)
        return ""


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _clean_extracted_content(url: str, raw_content: str) -> str:
    if not raw_content:
        return ""

    domain = _extract_domain(url)
    text = raw_content

    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+", "", text)

    if _is_social_domain(domain):
        text = _extract_social_post_text(text)

    cleaned_lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        low = line.lower()
        if (
            "%3csvg" in low
            or "%3e%3cpath" in low
            or "data:image/svg+xml" in low
            or "viewbox=" in low
            or "xmlns=" in low
            or "fill='url(" in low
        ):
            continue
        if re.fullmatch(r"[0-9.,kmb\s:]+", low):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def _is_social_domain(domain: str) -> bool:
    return domain in SOCIAL_DOMAINS


def _extract_social_post_text(text: str) -> str:
    """Extract likely author-post text and stop before comments/UI noise.

    Uses exact-match stop markers to avoid false positives on words like
    'share' or 'like' appearing in normal post content.
    """
    lines = [ln.strip() for ln in text.splitlines()]
    kept: list[str] = []
    started = False

    exact_stop_markers = {
        "comments",
        "all reactions",
        "most relevant",
        "top comments",
        "view more comments",
        "view more replies",
        "write a comment",
        "add a comment",
    }

    for line in lines:
        if not line:
            continue

        lower = line.lower().strip()

        if lower.startswith("## ") or lower.startswith("### ") or line == "---":
            continue
        if lower.startswith("[") and "](" in line and "·" in line:
            started = True
            continue
        if line.startswith("!["):
            break

        if lower in exact_stop_markers:
            break
        if "<svg" in lower or "data:image/svg+xml" in lower:
            break

        if not started and line.startswith("[**") and "](" in line:
            started = True
            continue

        if started or len(line.split()) > 4:
            kept.append(line)
            started = True

    return "\n".join(kept)
