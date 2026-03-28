"""Link fact-check handler -- extract article content, check domain credibility, fact-check claims."""

from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs

import httpx
from tavily import AsyncTavilyClient

from app.config import TAVILY_API_KEY
from app.engines.text_handler import fact_check_text
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
}

_VIDEO_PATH_PATTERNS = (
    re.compile(r"/reel/", re.IGNORECASE),
    re.compile(r"/reels/", re.IGNORECASE),
    re.compile(r"/video/", re.IGNORECASE),
    re.compile(r"/shorts/", re.IGNORECASE),
    re.compile(r"/watch", re.IGNORECASE),
    re.compile(r"/p/[A-Za-z0-9_-]+", re.IGNORECASE),
)


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


def _is_video_link(url: str) -> bool:
    """Detect whether a URL points to a video (YouTube, Instagram Reel, TikTok, etc.)."""
    domain = _extract_domain(url)
    if domain in VIDEO_DOMAINS:
        if domain in ("youtube.com", "m.youtube.com", "youtu.be"):
            return True
        for pat in _VIDEO_PATH_PATTERNS:
            if pat.search(url):
                return True
        if domain in ("tiktok.com", "vm.tiktok.com", "vimeo.com",
                       "dailymotion.com", "rumble.com", "bitchute.com", "odysee.com"):
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

    if _is_video_link(url):
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
    """Handle video links with a tiered approach:
    1. Try YouTube transcript (free, no download)
    2. Fall back to metadata + web search
    3. If nothing works, offer dual prompt to user
    """
    transcript = await _get_youtube_transcript(url) if _is_youtube(url) else ""

    if transcript:
        parts = ["📹 *Checking claims from this video transcript:*", ""]
        text_message, _ = await fact_check_text(transcript[:4000])
        parts.append(text_message)
        return "\n".join(parts)

    title, description = await _get_video_metadata(url)
    search_context = await _search_about_video(url, title) if title else ""

    combined = ""
    if title:
        combined = f"Video title: {title}"
    if description:
        combined = f"{combined}\nVideo description: {description[:1000]}".strip()
    if search_context:
        combined = f"{combined}\n\nWeb context about this video: {search_context}".strip()

    if combined:
        parts = [f"📹 *Checking claims from this video ({domain}):*", ""]
        text_message, _ = await fact_check_text(combined[:4000])
        parts.append(text_message)
        parts.append("")
        parts.append(
            "💡 _Note: I analyzed the video title, description, and web context. "
            "For the most accurate check, you can also type out the specific claim "
            "from the video as text._"
        )
        return "\n".join(parts)

    return (
        f"📹 *Video link from:* _{domain}_\n\n"
        "I couldn't extract content from this video link.\n\n"
        "You can help me check it in two ways:\n"
        "1️⃣ *Type the claim* — Write out the main claim from the video as text\n"
        "2️⃣ *Upload the video* — Download and send me the video directly, "
        "and I'll analyze the audio and visuals\n\n"
        "💡 _Option 1 is faster and works best for most forwarded videos!_"
    )


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
        from youtube_transcript_api import YouTubeTranscriptApi
        ytt = YouTubeTranscriptApi()
        transcript_list = ytt.fetch(video_id)
        text_parts = [entry.text for entry in transcript_list if hasattr(entry, "text")]
        full_text = " ".join(text_parts)
        logger.info("YouTube transcript: %d chars for %s", len(full_text), video_id)
        return full_text[:5000]
    except Exception:
        logger.info("No YouTube transcript available for %s", video_id)
        return ""


async def _get_video_metadata(url: str) -> tuple[str, str]:
    """Extract video title and description from Open Graph / HTML meta tags."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; TruthBot/1.0)"
            })
        if resp.status_code != 200:
            return "", ""

        html = resp.text[:50000]
        title = _extract_meta(html, "og:title") or _extract_meta(html, "title") or ""
        description = _extract_meta(html, "og:description") or _extract_meta(html, "description") or ""
        return title.strip(), description.strip()
    except Exception:
        logger.debug("Could not fetch video metadata for %s", url)
        return "", ""


def _extract_meta(html: str, name: str) -> str:
    """Extract content from a meta tag by property or name."""
    patterns = [
        re.compile(rf'<meta\s+property="{re.escape(name)}"\s+content="([^"]*)"', re.IGNORECASE),
        re.compile(rf'<meta\s+content="([^"]*)"\s+property="{re.escape(name)}"', re.IGNORECASE),
        re.compile(rf'<meta\s+name="{re.escape(name)}"\s+content="([^"]*)"', re.IGNORECASE),
        re.compile(rf'<meta\s+content="([^"]*)"\s+name="{re.escape(name)}"', re.IGNORECASE),
    ]
    if name == "title":
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        if title_match:
            return title_match.group(1).strip()
    for pat in patterns:
        m = pat.search(html)
        if m:
            return m.group(1)
    return ""


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
