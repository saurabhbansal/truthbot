# TruthBot — Full Project Context

> **Read this file first.** It contains everything you need to continue working on TruthBot — architecture, design decisions, what's built, what's pending, prompt tuning history, and setup instructions. After reading this, create the `.env` file by asking the user for their API keys.

---

## What is TruthBot?

A **WhatsApp fact-checker bot** for personal use among friends and family. Users forward suspicious messages, images, videos, or links to TruthBot, and it tells them if the content is real, fake, or misleading.

- **Target users**: Non-technical family members (parents, uncles, aunts) in India
- **Primary problem**: AI-generated videos, fake health claims, political misinformation, WhatsApp chain forwards
- **Interaction model**: Forward-to-bot (1:1 chat). Group chat @mention is a future feature.
- **Name**: TruthBot
- **Tone**: Friendly, conversational — like a helpful cousin who's good at Googling, not a news anchor
- **Language**: English for MVP. Hindi is Phase 1.5 (low effort since LLMs generate Hindi natively)
- **Status**: Live on WhatsApp

---

## Architecture Overview

```
WhatsApp User
    │
    ▼
Meta WhatsApp Cloud API (webhook + HMAC signature verification)
    │
    ▼
FastAPI Server (app/main.py)
    │
    ▼
Daily Usage Limits Check (per-user + global)
    │
    ▼
Content Router (app/router/content_router.py)
    │
    ├── Text → Claim Extractor → 3-Layer Source Search → Verdict Engine (GPT-4o) → Formatter
    ├── Image → GPT-4o Vision + OCR (Google Vision) → Text Pipeline
    ├── Video → ffmpeg frame/audio extraction → GPT-4o Vision + Whisper → Text Pipeline
    ├── Link (article) → Domain Classification + Article Extraction (Tavily) → Text Pipeline
    ├── Link (video) → YouTube Transcript / Metadata+Search Fallback / Dual User Prompt
    ├── Audio → "Coming soon" message
    └── Interactive → Feedback Handler
    │
    ▼
WhatsApp Reply (verdict + sources + feedback buttons)
```

---

## 3-Layer Source Trust Architecture (Layer 4 Dropped)

Sources are searched in parallel and weighted by trust. Layer 4 (general web) was removed to save Tavily API credits.

| Layer | Source | Trust Weight | What It Does |
|-------|--------|-------------|-------------|
| **L1** | Google Fact Check Tools API | 1.0 (highest) | Searches IFCN-certified fact-checkers (BOOM, Alt News, Snopes, AFP, etc.) |
| **L2** | Official Sources (Tavily, basic depth) | 0.85 | Targeted search on .gov, .edu, RBI, WHO, PIB, ICMR, NASA, etc. |
| **L3** | News Outlets (Tavily, basic depth) | 0.6 | Search filtered to curated allowlist (NDTV, The Hindu, Reuters, BBC, etc.) |

**Cost optimizations applied:**
- Tavily search depth downgraded from `advanced` to `basic` (1 credit vs 2 credits per search)
- Fact-check short-circuit: if Layer 1 returns 2+ results, Layers 2-3 are skipped entirely (saves 2 Tavily credits)
- Evidence caching: 24h TTL cache prevents re-searching the same claim
- Layer 4 (general web) dropped entirely

Confidence scoring: base score from highest layer that returned results + bonus for multiple layers agreeing + bonus for multiple sources within a layer.

---

## LLM Model Split

| Task | Model | Why |
|------|-------|-----|
| Claim extraction | gpt-4o-mini | Fast, cheap, structured output |
| Claim translation | gpt-4o-mini | Simple translation task |
| Verdict reasoning | gpt-4o | Higher quality reasoning, thorough explanations |
| Image analysis | gpt-4o (Vision) | Visual understanding, text extraction, AI detection |
| Video frame analysis | gpt-4o (Vision) | Multi-frame visual analysis |
| Audio transcription | gpt-4o-mini-transcribe | Cost-effective speech-to-text |

---

## 9 Verdict Labels

```
HIGH CONFIDENCE:
  ✅ TRUE              — Verified by multiple reliable sources
  ❌ FALSE             — Debunked, or major event with zero corroboration

PARTIAL TRUTH (5 patterns):
  ⚠️ MISLEADING        — Pattern A: True fact + false conclusion
  🔴 MOSTLY FALSE      — Pattern B: Right topic, wrong numbers/details
  🕐 OUTDATED          — Pattern C: Was true, no longer current
  🔍 MISSING CONTEXT   — Pattern D: True stats, misleading framing
  🔄 OUT OF CONTEXT    — Pattern E: Real media, wrong attribution

LOW CONFIDENCE:
  ❓ UNVERIFIED        — ONLY for obscure/niche claims with zero related info

SPECIAL:
  🤖 AI-GENERATED      — Image/video detected as AI-made
```

---

## Anti-Hallucination Pipeline (4 Steps)

1. **Search FIRST, reason SECOND** — The LLM never generates a verdict from its own knowledge. It first searches all source layers, then synthesizes a verdict from the retrieved evidence only.
2. **Mandatory citation** — Every factual statement in the verdict must cite a specific source from the search results.
3. **Source validation** — Only sources actually returned by the search APIs are allowed.
4. **Confidence calibration** — Final confidence = 40% LLM self-assessed + 60% source-layer confidence.

---

## Image Processing Pipeline (GPT-4o Vision)

Hive Moderation API has been **removed**. GPT-4o Vision is now the primary engine for all image analysis:

1. **GPT-4o Vision analysis** (parallel with OCR):
   - Visual description (people, objects, logos, screenshots)
   - Text transcription from image (headlines, captions, watermarks, social media posts)
   - Claim identification from visual and textual content
   - AI-generated/manipulated/deepfake assessment
2. **Google Cloud Vision OCR** (DOCUMENT_TEXT_DETECTION, upgraded from TEXT_DETECTION)
3. **AI detection**: Keywords in Vision analysis trigger "POSSIBLE AI-GENERATED IMAGE" warning
4. **Combined fact-checking**: Caption + OCR text + Vision analysis all fed into text pipeline

---

## Video Processing Pipeline (ffmpeg + GPT-4o Vision + Whisper)

Complete rewrite from the old Hive-only approach:

1. **Write video to temp file**
2. **ffmpeg frame extraction**: 4 evenly-spaced frames from the video
3. **ffmpeg audio extraction**: MP3 at 64kbps, mono, 16kHz, max 120 seconds
4. **GPT-4o Vision on frames** (parallel with audio transcription):
   - Multi-frame visual analysis (description, text, claims, AI assessment, continuity)
   - Uses `detail: "low"` to reduce token cost
5. **Whisper transcription** (gpt-4o-mini-transcribe): Audio → text
6. **AI detection**: Same keyword-based check as images
7. **Combined fact-checking**: Caption + transcript + vision analysis → text pipeline

**Requirements**: ffmpeg must be installed (added to Dockerfile via `apt-get install ffmpeg`)

---

## Video Link Handling (Tiered Fallback)

For YouTube, Instagram Reels, TikTok, and other video links:

1. **Tier 1 — YouTube Transcript** (free, no download): Uses `youtube-transcript-api` to fetch captions
2. **Tier 2 — Metadata + Web Search**: Fetches OG meta tags (title, description) + Tavily search for context
3. **Tier 3 — Dual User Prompt**: If nothing works, offers two options:
   - "Type the claim" (faster, works for most forwards)
   - "Upload the video directly" (triggers full video pipeline)

---

## Daily Usage Limits

| Limit | Value | Purpose |
|-------|-------|---------|
| Per-user daily total | 30 checks | Prevent single user from exhausting budget |
| Per-user daily videos | 5 | Videos are most expensive (Vision + Whisper) |
| Per-user daily images | 10 | Images use Vision API |
| Global daily total | 500 checks | Hard cap to prevent cost overruns |

Tracked in `daily_usage` SQLite table. Checked before processing in content router.

---

## Database Schema (SQLite)

Five tables with indexes:

```sql
-- Verdict caching (24h TTL, hash-based dedup)
cache: content_hash (PK), verdict_json, created_at

-- Evidence caching (24h TTL, prevents re-searching same claim)
evidence_cache: claim_hash (PK), evidence_json, created_at

-- User feedback on verdicts
feedback: id, verdict_id, user_phone_hash, feedback_type, negative_reason,
          source_link, source_quality, free_text, created_at

-- Usage tracking (statistics)
usage_stats: id, user_phone_hash, message_type, verdict_label,
             confidence, processing_ms, created_at

-- Daily usage limits
daily_usage: id, user_phone_hash, message_type, date, created_at
```

Indexes on: cache(created_at), evidence_cache(created_at), feedback(verdict_id), usage_stats(user_phone_hash), usage_stats(created_at), daily_usage(user_phone_hash, date), daily_usage(date).

Phone numbers are never stored — only SHA-256 hashes (first 16 chars).

Periodic cache sweep runs every 6 hours to remove expired entries.

---

## India-Specific Source Priorities

| Category | Sources |
|----------|---------|
| Government fact-check | PIB Fact Check (pibfactcheck.in) |
| Indian fact-checkers | BOOM Live, Alt News, Factly, Newschecker, The Quint (all IFCN-certified) |
| Government policy | pib.gov.in, india.gov.in, mha.gov.in |
| Financial | rbi.org.in, sebi.gov.in, incometaxindia.gov.in, gst.gov.in |
| Health | icmr.gov.in, mohfw.gov.in, aiims.edu |
| Science/Space | isro.gov.in, dst.gov.in |
| Weather/Disaster | imd.gov.in |
| Indian news | NDTV, The Hindu, Indian Express, Hindustan Times, The Wire, Scroll.in, LiveMint |

---

## Key Design Decisions (and WHY)

### 1. FALSE vs UNVERIFIED
For major public events, absence of coverage across official sources and news outlets IS strong evidence of falsehood. UNVERIFIED is ONLY for truly obscure/niche claims.

### 2. No Confidence Indicator Shown to Users
Confidence is baked into the TONE of the response (high → direct, medium → softer + tip, low → cautious + tip).

### 3. No Source Credibility Label for Links
Only blocked domains show a warning. Source credibility is factored into the verdict via the trust system.

### 4. Strict Neutrality
8 explicit neutrality rules in the verdict prompt. Never praise/criticize any government, party, leader, religion, or community.

### 5. GPT-4o Vision Replaces Hive
Hive Moderation API removed. GPT-4o Vision handles all image/video understanding including AI detection, text extraction, and claim identification in a single call.

### 6. Claim Extraction Preserves Original Meaning
Claims extracted exactly as stated. Grounding filter uses 70% token overlap (relaxed from 85%). If filter drops ALL claims, originals are returned as fallback.

### 7. Feedback on Every Verdict
Interactive WhatsApp buttons (Helpful / Not Helpful / Wrong) sent after every verdict. Feedback sending is in a separate try/except so failures don't trigger "Oops" messages.

### 8. Broad Sensitive Generalizations Are Not Fact-Checked
Communal/religious generalizations get a neutral redirect asking for a specific incident.

### 9. Webhook HMAC Signature Verification
X-Hub-Signature-256 header verified using META_APP_SECRET. Gracefully disabled if secret not set.

### 10. Rate-Limited Users Get Silently Dropped
Rate-limited users no longer receive a "slow down" message (which itself counts as a message). They're silently skipped.

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Server | FastAPI + Uvicorn | Webhook server |
| LLM (extraction) | OpenAI GPT-4o-mini | Claim extraction, translation |
| LLM (verdict) | OpenAI GPT-4o | Verdict reasoning, image/video analysis |
| Audio transcription | OpenAI gpt-4o-mini-transcribe | Video audio → text |
| Fact-Check DB | Google Fact Check Tools API | Layer 1 source |
| Web Search | Tavily API (basic depth) | Layers 2, 3 + article extraction |
| OCR | Google Cloud Vision API (DOCUMENT_TEXT_DETECTION) | Text extraction from images |
| Video processing | ffmpeg | Frame extraction, audio extraction |
| YouTube transcripts | youtube-transcript-api | Free transcript fetching |
| Database | SQLite (aiosqlite) | Caching, feedback, usage stats, daily limits |
| Messaging | WhatsApp Cloud API | Receive/send messages, media download |
| Deployment | Docker + Railway | Cloud hosting (ffmpeg in Docker image) |
| Repo | github.com/saurabhbansal/truthbot | Private repo |

---

## File Structure

```
truthbot/
├── app/
│   ├── main.py                    # FastAPI app, health + stats + legal endpoints + cache sweep
│   ├── config.py                  # Environment variables loader + validation
│   ├── router/
│   │   └── content_router.py      # Message dispatcher + daily usage limit checks
│   ├── engines/
│   │   ├── claim_extractor.py     # LLM claim extraction + translation + grounding filter (70% threshold)
│   │   ├── verdict_engine.py      # Core verdict logic (GPT-4o, 2500 tokens, expanded evidence)
│   │   ├── text_handler.py        # Full text pipeline + sensitive content guard + empty input guard
│   │   ├── image_handler.py       # GPT-4o Vision + OCR + AI detection + text pipeline
│   │   ├── video_handler.py       # ffmpeg + GPT-4o Vision + Whisper + text pipeline
│   │   ├── link_handler.py        # Domain classification + video link handling + article extraction
│   │   ├── ocr.py                 # Google Cloud Vision OCR (DOCUMENT_TEXT_DETECTION)
│   │   └── hive_detector.py       # DEPRECATED — no longer imported (kept for reference)
│   ├── sources/
│   │   ├── allowlists.py          # 50+ trusted domains, 14 blocked domains
│   │   ├── fact_check_db.py       # Layer 1: Google Fact Check API (with HTTP status checks)
│   │   ├── official_sources.py    # Layer 2: Official .gov/.edu search (basic depth)
│   │   ├── news_sources.py        # Layer 3: Curated news outlets (basic depth, sorted domains)
│   │   ├── web_search.py          # Layer 4: UNUSED (kept for reference, not called)
│   │   └── source_trust.py        # Aggregates L1-L3, evidence caching, fact-check short-circuit
│   ├── verdict/
│   │   ├── confidence.py          # Verdict labels enum, confidence thresholds
│   │   └── formatter.py           # WhatsApp formatting + safe source access + multi-verdict synthesis
│   ├── feedback/
│   │   └── feedback_handler.py    # Interactive buttons, follow-up, DB logging (body_text fix)
│   ├── db/
│   │   ├── database.py            # SQLite init (5 tables + 7 indexes)
│   │   ├── cache.py               # Hash-based verdict + evidence caching (24h TTL, periodic sweep)
│   │   └── usage.py               # Usage stats + daily limits (per-user, per-type, global)
│   ├── whatsapp/
│   │   ├── webhook.py             # GET verify + POST receive + HMAC signature verification
│   │   ├── sender.py              # Send text, buttons, lists to WhatsApp
│   │   └── media.py               # Download media + size limits + content-type validation
│   └── utils/
│       ├── logger.py              # Logging utility
│       └── rate_limiter.py        # In-memory rate limiter (5 req/min, periodic cleanup)
├── test_cli.py                    # Interactive CLI test harness
├── test_webhook.py                # Webhook payload simulator
├── requirements.txt               # Python dependencies (includes youtube-transcript-api)
├── Dockerfile                     # Docker containerization (includes ffmpeg)
├── Procfile                       # Railway process file
├── railway.toml                   # Railway config
├── CONTEXT.md                     # This file
├── GUIDE.md                       # "How to Use TruthBot" guide for family
├── README.md                      # Quick start + architecture overview
├── PRIVACY_POLICY.md              # Privacy policy (for Meta app review)
├── TERMS_OF_SERVICE.md            # Terms of service (for Meta app review)
├── DATA_DELETION.md               # Data deletion instructions (for Meta app review)
└── .env.example                   # API key template
```

---

## Cost Estimate (Monthly, $5 OpenAI Budget)

| Service | Free Tier | Cost Per Request | Notes |
|---------|-----------|-----------------|-------|
| WhatsApp Cloud API | 1,000 conversations/month | $0 | Family use stays within free tier |
| OpenAI GPT-4o-mini (extraction) | Pay per token | ~$0.001/request | Very cheap |
| OpenAI GPT-4o (verdict) | Pay per token | ~$0.01-0.02/request | Main cost driver for text |
| OpenAI GPT-4o Vision (image) | Pay per token | ~$0.03-0.05/request | High-detail image analysis |
| OpenAI GPT-4o Vision (video) | Pay per token | ~$0.04-0.08/request | 4 frames at low detail |
| OpenAI Whisper (video audio) | Pay per minute | ~$0.006/min | Cost-effective transcription |
| Tavily API | 1,000 credits/month free | 1 credit/basic search | ~2 searches per claim (L2+L3) |
| Google Fact Check API | Free | $0 | Always free |
| Google Cloud Vision (OCR) | 1,000 images/month free | $0 | Stays within free tier |
| Railway hosting | $5/month starter | $5 | Fixed cost |

**With $5 OpenAI budget**: ~200-300 text checks, ~80-100 image checks, ~50-70 video checks per month.

---

## Bugs Fixed (Complete Overhaul)

### P0 — Critical (Crash/Complete Failure)
- P0-1: `send_buttons()` called with `body=` instead of `body_text=` → feedback buttons never appeared
- P0-2: SQLite UPDATE with ORDER BY/LIMIT (invalid syntax) → feedback reason never saved
- P0-3: Single try/except wrapped verdict + feedback → feedback failure triggered "Oops" message
- P0-4: Images had no visual understanding (only generic OCR + Hive labels) → GPT-4o Vision
- P0-5: Videos had no content analysis (only Hive deepfake) → ffmpeg + Vision + Whisper
- P0-6: Video links (YouTube, Instagram, TikTok) completely failed → tiered fallback
- P0-7: Single claim failure crashed entire pipeline → `return_exceptions=True` + filtering

### P1 — High (Quality/Accuracy)
- P1-1: Verdict model upgraded from gpt-4o-mini to gpt-4o
- P1-2: Verdict max_tokens increased from 800 to 2500
- P1-3: Verdict prompt relaxed (no length limits on explanation)
- P1-4: Evidence snippets expanded from 300 to 800 chars
- P1-5: Multi-verdict format now includes explanations + overall synthesis
- P1-7: Claim extractor fallback returns [] instead of raw text
- P1-8: HTTP status code checks on Google Fact Check API and Vision API
- P1-9: Grounding filter relaxed to 70% overlap + fallback if all claims dropped
- P1-10: Media size limits (10MB image, 16MB video) with pre/post-download checks

### P2 — Medium (Infrastructure)
- P2-1: DB connection leak fixed (all get_db() calls use try/finally close)
- P2-2: Webhook HMAC signature verification (X-Hub-Signature-256)
- P2-4: Rate limiter periodic cleanup (prevents unbounded memory growth)
- P2-5: Tavily downgraded to basic search depth (cost optimization)
- P2-6: Confidence parsing hardened (try/except + clamping to 0-1)
- P2-7: Formatter uses safe .get() for source dicts (no KeyError)
- P2-10: Input text capped at 8000 chars
- P2-11: Database indexes added on all frequently-queried columns
- P2-12: Periodic cache sweep (every 6 hours)

### P3 — Low (Cleanup)
- P3-1: Unused imports removed (video_handler rewritten)
- P3-2: News domain list sorted for deterministic slicing
- P3-3: Empty input guard in text_handler
- P3-5: Rate-limited users silently dropped (no reply message)
- P3-6: datetime.utcnow() replaced with timezone-aware datetime
- P3-7: rate_limiter.remaining() now prunes before counting
- P3-8: Content-type validation via magic bytes on media download
- P3-9: classify_url handles empty domain gracefully
- P3-10: Config warns if META_APP_SECRET not set

---

## API Keys Required

```env
# WhatsApp Cloud API
WHATSAPP_ACCESS_TOKEN=<paste_token>
WHATSAPP_PHONE_NUMBER_ID=<paste_id>
WHATSAPP_BUSINESS_ACCOUNT_ID=<paste_id>
META_APP_SECRET=<paste_secret>
WHATSAPP_VERIFY_TOKEN=<any_random_string_you_choose>

# OpenAI (used for extraction, verdict, vision, whisper)
OPENAI_API_KEY=<paste_key>
OPENAI_MODEL=gpt-4o-mini
OPENAI_VERDICT_MODEL=gpt-4o

# Tavily (web search for Layers 2, 3)
TAVILY_API_KEY=<paste_key>

# Google Cloud (Fact Check API + Vision OCR)
GOOGLE_API_KEY=<paste_key>
```

Note: `HIVE_API_KEY` is no longer required (Hive has been replaced by GPT-4o Vision).

---

## Setup Instructions (New Machine)

```bash
# 1. Clone the repo
git clone https://github.com/saurabhbansal/truthbot.git
cd truthbot

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install ffmpeg (for video processing)
# macOS: brew install ffmpeg
# Ubuntu: sudo apt-get install ffmpeg
# Docker: already included in Dockerfile

# 5. Create .env file (Cursor agent should create this and ask for keys)

# 6. Test locally
python test_cli.py

# 7. Run the server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Dependencies (requirements.txt)

```
fastapi==0.115.12
uvicorn[standard]==0.34.0
httpx==0.28.1
python-dotenv==1.1.0
openai==1.68.2
tavily-python==0.5.0
google-cloud-vision==3.9.0
pydantic==2.11.1
python-multipart==0.0.20
aiosqlite==0.21.0
youtube-transcript-api==1.0.3
```

---

## Future Roadmap (Not Started)

| Feature | Effort | Priority | Notes |
|---------|--------|----------|-------|
| Hindi responses | Low | High | LLMs generate Hindi natively |
| Audio/voice note checking | Low | High | Whisper already integrated for video; just need audio routing |
| Group chat @mention | High | Low | Complex permissions |
| Reverse image search | Medium | Medium | Google Lens API or TinEye |
| Automated bias testing | Medium | Medium | Same claim from both sides |
| Advanced feedback validation | Medium | Low | Consensus scoring, user track record |
| Admin dashboard | Medium | Low | Web UI for stats and trends |

---

## Instructions for Cursor Agent

When the user says "read CONTEXT.md", do the following:

1. Read this entire file to understand the project
2. Check if `.env` exists in the project root
3. If `.env` does NOT exist:
   - Create it using the template in the "API Keys Required" section above
   - Ask the user to paste each API key one by one
   - Save the file
4. Verify the setup works: `python -c "from app.main import app; print('OK:', app.title)"`
5. Ask the user what they want to do next (test, fix, deploy, etc.)
