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
- **Language**: English + Hindi + regional Indian languages (Gemini handles natively)
- **Status**: Live on WhatsApp

---

## Architecture Overview

```
WhatsApp User
    │
    ▼
Meta WhatsApp Cloud API (webhook + HMAC signature + message deduplication)
    │
    ▼
FastAPI Server (app/main.py)
    │
    ▼
Daily Usage Limits Check (per-user + per-type + global)
    │
    ▼
Content Router (app/router/content_router.py)
    │
    ├── Text → Claim Extractor (Gemini Flash) → 3-Layer Source Search → Verdict Engine (Gemini Pro) → Formatter
    ├── Image → Gemini 2.5 Pro image analysis (fallback: GPT-4o, escalate GPT-5.4) + OCR → Text Pipeline
    ├── Video → Gemini 2.5 Pro native video analysis (fallback: ffmpeg+Vision+Whisper) → Text Pipeline
    ├── Audio/Voice → Gemini 2.5 Pro native audio analysis → Text Pipeline
    ├── Link (article) → Domain Classification + Article Extraction (Tavily) → Text Pipeline
    ├── Link (video) → 4-tier hybrid (yt-dlp metadata/subtitles/search/download) → Text Pipeline
    └── Interactive → Feedback Handler
    │
    ▼
WhatsApp Reply (verdict-first format + sources + feedback buttons)
```

---

## 3-Layer Source Trust Architecture

Sources are searched in parallel and weighted by trust. Layer 4 (general web) was removed to save Tavily API credits. Gemini Grounding with Google Search serves as overflow fallback when Tavily credits are exhausted.

| Layer | Source | Trust Weight | What It Does |
|-------|--------|-------------|-------------|
| **L1** | Google Fact Check Tools API | 1.0 (highest) | Searches IFCN-certified fact-checkers (BOOM, Alt News, Snopes, AFP, etc.) |
| **L2** | Official Sources (Tavily, basic depth) | 0.85 | Targeted search on .gov, .edu, RBI, WHO, PIB, ICMR, NASA, etc. |
| **L3** | News Outlets (Tavily, basic depth) | 0.6 | Search filtered to curated allowlist (NDTV, The Hindu, Reuters, BBC, etc.) |
| **Fallback** | Gemini Grounding with Google Search | 0.5 | Kicks in when Tavily L2+L3 return empty (credits exhausted) |

**Cost optimizations applied:**
- Tavily search depth downgraded from `advanced` to `basic` (1 credit vs 2 credits per search)
- Fact-check short-circuit: if Layer 1 returns 2+ results, Layers 2-3 are skipped entirely (saves 2 Tavily credits)
- Evidence caching: 24h TTL cache prevents re-searching the same claim
- Verdict caching: 24h TTL cache prevents re-checking identical text
- Layer 4 (general web) dropped entirely
- Gemini Grounding fallback is free (within Gemini API free tier)

Confidence scoring: base score from highest layer that returned results + bonus for multiple layers agreeing + bonus for multiple sources within a layer.

---

## LLM Model Architecture (Stabilized Hybrid: Option C)

| Task | Primary Model | Fallback | Why |
|------|--------------|----------|-----|
| Claim extraction | Gemini 2.5 Flash | — | Best multilingual, structured output, cost-efficient |
| Claim translation | Gemini 2.5 Flash | — | Google's multilingual heritage, Hindi/regional native |
| Verdict reasoning | Gemini 2.5 Pro | OpenAI GPT-5.4 | Strong reasoning with premium fallback quality |
| Image analysis | OpenAI GPT-4o | OpenAI GPT-5.4 (escalate on weak output), Gemini Pro (last resort) | Better real-world quality stability with controlled escalation |
| Video analysis | Gemini 2.5 Pro (native) | ffmpeg + GPT-5.4 Vision + Whisper | Single API call replaces 4-step pipeline |
| Audio analysis | Gemini 2.5 Pro (native) | OpenAI Whisper | Supports Hindi + regional languages with robust fallback |
| OCR | Google Cloud Vision | — | Works well, no change needed |

**Cost model**: Gemini handles extraction/translation/verdict/video-audio primary paths; OpenAI focuses on image primary plus controlled fallback/escalation. Production requires billed Gemini quota because free-tier limits are too low for burst traffic.

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

## Image Processing Pipeline (Option C: OpenAI Vision Primary)

1. **OpenAI GPT-4o image analysis** (parallel with OCR):
   - Visual description (people, objects, logos, screenshots)
   - Text transcription from image (headlines, captions, watermarks, social media posts)
   - Claim identification from visual and textual content
   - AI-generated/manipulated/deepfake assessment
   - Correct MIME type detection (JPEG, PNG, WebP via magic bytes)
2. **Escalation policy**:
   - Escalate to OpenAI GPT-5.4 when GPT-4o output is weak/ambiguous
   - Last-resort fallback: Gemini 2.5 Pro when OpenAI path is unavailable
3. **Google Cloud Vision OCR** (DOCUMENT_TEXT_DETECTION)
4. **AI detection**: Keywords in image analysis trigger "POSSIBLE AI-GENERATED IMAGE" warning
5. **Combined fact-checking**: Caption + OCR text + analysis text all fed into text pipeline

---

## Video Processing Pipeline (Gemini 2.5 Pro Native)

Primary pipeline (single API call):
1. Upload video to Gemini Files API
2. Gemini 2.5 Pro analyzes visuals + audio + text overlays in one call
3. Supports Hindi and all regional languages natively
4. AI-generated/deepfake assessment included
5. Combined analysis fed into text pipeline

Fallback pipeline (if Gemini fails):
1. ffmpeg frame extraction (4 evenly-spaced frames)
2. ffmpeg audio extraction (MP3, 64kbps, mono, 16kHz, max 120s)
3. GPT-5.4 Vision on frames + Whisper transcription (parallel)
4. Combined analysis fed into text pipeline

**Requirements**: ffmpeg must be installed (added to Dockerfile via `apt-get install ffmpeg`)

---

## Audio/Voice Note Pipeline (Gemini 2.5 Pro Native)

1. Write audio bytes to temp file
2. Upload to Gemini Files API
3. Gemini 2.5 Pro transcribes + analyzes audio natively
4. Supports Hindi and all regional languages
5. If Gemini fails, OpenAI Whisper fallback transcription is used
6. Transcript fed into text pipeline for fact-checking

---

## Video Link Handling (4-Tier Hybrid Pipeline)

For YouTube, Instagram Reels, TikTok, X, Facebook, Snapchat, Reddit, and other video links:

1. **Tier 1 — yt-dlp Metadata** (no download, 2-3s): Title, description, duration
2. **Tier 2 — Transcript** (youtube-transcript-api + yt-dlp subtitles): Supports en, hi, ta, te, bn, mr, gu, kn, ml, pa
3. **Tier 3 — Metadata + Web Search**: If transcript too short, search web for existing fact-checks
4. **Tier 4 — Full Download + Gemini Analysis**: Download via yt-dlp (max 50MB) → Gemini 2.5 Pro native analysis

Video links count against the "video" daily limit (same as uploaded videos).

---

## Daily Usage Limits

| Limit | Value | Purpose |
|-------|-------|---------|
| Per-user daily total | 30 checks | Prevent single user from exhausting budget |
| Per-user daily videos | 5 | Videos are most expensive |
| Per-user daily images | 10 | Images use Vision API |
| Per-user daily audio | 10 | Audio uses Gemini Pro |
| Global daily total | 500 checks | Hard cap to prevent cost overruns |

Tracked in `daily_usage` SQLite table. Checked before processing in content router. Video links share the video limit.

---

## Database Schema (SQLite)

Core tables with indexes:

```sql
-- Verdict caching (24h TTL, hash-based dedup)
cache: content_hash (PK), verdict_json, created_at

-- Evidence caching (24h TTL, prevents re-searching same claim)
evidence_cache: claim_hash (PK), evidence_json, created_at

-- User feedback on verdicts
feedback: id, verdict_id, user_phone_hash, feedback_type, negative_reason,
          source_link, source_quality, free_text, created_at

-- Verdict context mapping for feedback-learning loops
verdict_context: verdict_id (PK), content_hash, message_type, created_at

-- Usage tracking (statistics)
usage_stats: id, user_phone_hash, message_type, verdict_label,
             confidence, processing_ms, created_at

-- Daily usage limits
daily_usage: id, user_phone_hash, message_type, date, created_at
```

Indexes on: cache(created_at), evidence_cache(created_at), feedback(verdict_id), verdict_context(content_hash), usage_stats(user_phone_hash), usage_stats(created_at), daily_usage(user_phone_hash, date), daily_usage(date).

Phone numbers are never stored — only SHA-256 hashes (first 16 chars).

Periodic maintenance runs every 6 hours:
- cache and evidence cache TTL cleanup (24h)
- retention cleanup for daily_usage (35d), usage_stats (90d), feedback (90d), verdict_context (90d)

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

### 5. All-Gemini Primary Architecture
Gemini 2.5 Pro for verdicts + video/audio (free tier: 1,500 req/day). Gemini 2.5 Flash for claim extraction + translation (free tier: 1,500 req/day). OpenAI is used as targeted fallback (verdict/image/audio), enabling $0-5/month operation for 25 users.

### 6. Verdict-First Response Format
Overall verdict (emoji + bold label + summary) appears at the top. Per-claim details are concise for clear-cut verdicts (1-2 sentences) and fuller for nuanced verdicts. Sources consolidated at bottom.

### 7. Claim Extraction Preserves Original Meaning
Claims extracted exactly as stated. Grounding filter uses 70% token overlap (relaxed from 85%). If filter drops ALL claims, originals are returned as fallback.

### 8. Feedback on Every Verdict
Interactive WhatsApp buttons (Helpful / Not Helpful) are sent after every verdict. If Not Helpful is selected, users choose a reason (Wrong verdict, Missing context, Bad sources, Unclear explanation, Other). Users can revise feedback; latest state is stored.

### 9. Broad Sensitive Generalizations Are Not Fact-Checked
Communal/religious generalizations get a neutral redirect asking for a specific incident.

### 10. Webhook HMAC Signature Verification + Message Deduplication
X-Hub-Signature-256 header verified using META_APP_SECRET. In-memory dedup prevents duplicate processing on webhook retries (120s TTL).

---

## Content Type Coverage

| Content Type | Supported | Pipeline |
|-------------|-----------|----------|
| Text | Yes | Gemini Flash extract → Gemini Pro verdict |
| Image | Yes | Gemini Pro image analysis + OCR → Gemini Pro verdict (fallback path to OpenAI) |
| Image + caption | Yes | Same + caption prepended |
| Video (uploaded) | Yes | Gemini 2.5 Pro native analysis → Gemini Pro verdict |
| Video + caption | Yes | Same + caption prepended |
| Video link (YouTube, Instagram, TikTok, X, etc.) | Yes | 4-tier hybrid → Gemini 2.5 Pro for Tier 4 |
| Audio/voice note | Yes | Gemini 2.5 Pro native audio → Gemini Pro verdict |
| Audio + caption | Yes | Same + caption prepended |
| Article link | Yes | Tavily extract → Gemini Pro verdict |
| Hindi/regional language content | Yes | Gemini handles natively (no language hardcoding) |

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Server | FastAPI + Uvicorn | Webhook server |
| LLM (extraction) | Gemini 2.5 Flash | Claim extraction, translation |
| LLM (verdict) | Gemini 2.5 Pro (fallback: OpenAI GPT-5.4) | Verdict reasoning |
| LLM (image) | OpenAI GPT-4o (escalate GPT-5.4, last-resort Gemini Pro) | Image analysis |
| LLM (video/audio) | Gemini 2.5 Pro (native multimodal) | Video + audio analysis |
| Fact-Check DB | Google Fact Check Tools API | Layer 1 source |
| Web Search | Tavily API (basic depth) + Gemini Grounding fallback | Layers 2, 3 + article extraction |
| OCR | Google Cloud Vision API (DOCUMENT_TEXT_DETECTION) | Text extraction from images |
| Video processing | ffmpeg (fallback only) | Frame extraction, audio extraction |
| Video links | yt-dlp + youtube-transcript-api | Metadata, subtitles, downloads |
| Database | SQLite (aiosqlite) | Caching, feedback, usage stats, daily limits |
| Messaging | WhatsApp Cloud API | Receive/send messages, media download |
| Deployment | Docker + Railway | Cloud hosting (ffmpeg in Docker image) |
| Repo | github.com/saurabhbansal/truthbot | Private repo |

---

## File Structure

```
truthbot/
├── app/
│   ├── main.py                    # FastAPI app, health + stats + runtime-metrics + legal endpoints + cache sweep
│   ├── config.py                  # Environment variables loader + validation (Gemini + OpenAI)
│   ├── router/
│   │   └── content_router.py      # Message dispatcher + daily usage limit checks + log_usage
│   ├── engines/
│   │   ├── gemini_client.py       # Shared Gemini API client (google-genai SDK)
│   │   ├── claim_extractor.py     # Gemini Flash claim extraction + translation + grounding filter
│   │   ├── verdict_engine.py      # Gemini Pro verdict logic (OpenAI GPT-5.4 fallback)
│   │   ├── text_handler.py        # Full text pipeline + verdict caching + sensitive content guard
│   │   ├── image_handler.py       # OpenAI-primary image analysis + OCR + targeted escalation
│   │   ├── retry_utils.py         # Bounded retry/backoff + rate-limit/transient error helpers
│   │   ├── video_handler.py       # Gemini Pro native video (fallback: ffmpeg+Vision+Whisper)
│   │   ├── audio_handler.py       # Gemini Pro native audio analysis
│   │   ├── link_handler.py        # 4-tier video link pipeline + article extraction
│   │   └── ocr.py                 # Google Cloud Vision OCR (DOCUMENT_TEXT_DETECTION)
│   ├── sources/
│   │   ├── allowlists.py          # 50+ trusted domains, 14 blocked domains
│   │   ├── fact_check_db.py       # Layer 1: Google Fact Check API
│   │   ├── official_sources.py    # Layer 2: Official .gov/.edu search (Tavily, basic depth)
│   │   ├── news_sources.py        # Layer 3: Curated news outlets (Tavily, basic depth)
│   │   ├── web_search.py          # Layer 4: UNUSED (kept for reference, not called)
│   │   └── source_trust.py        # Aggregates L1-L3 + Gemini Grounding fallback + caching
│   ├── verdict/
│   │   ├── confidence.py          # Verdict labels enum, confidence thresholds
│   │   └── formatter.py           # Verdict-first WhatsApp formatting + multi-verdict synthesis
│   ├── monitoring/
│   │   └── runtime_metrics.py     # In-memory counters for quota/parse/fallback/success signals
│   ├── feedback/
│   │   └── feedback_handler.py    # 2-step feedback flow, revision handling, dashboard query helpers
│   ├── db/
│   │   ├── database.py            # SQLite init (5 tables + 7 indexes)
│   │   ├── cache.py               # Hash-based verdict + evidence caching (24h TTL, periodic sweep)
│   │   └── usage.py               # Usage stats + daily limits (per-user, per-type, global)
│   ├── whatsapp/
│   │   ├── webhook.py             # GET verify + POST receive + HMAC + message deduplication
│   │   ├── sender.py              # Send text, buttons, lists to WhatsApp
│   │   └── media.py               # Download media + size limits + content-type validation (image/video/audio)
│   └── utils/
│       ├── logger.py              # Logging utility
│       └── rate_limiter.py        # In-memory rate limiter (5 req/min, periodic cleanup)
├── test_cli.py                    # Interactive CLI test harness
├── test_webhook.py                # Webhook payload simulator
├── requirements.txt               # Python dependencies
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

## Cost Estimate (Monthly, All-Gemini Architecture)

| Service | Free Tier | Cost Per Request | Notes |
|---------|-----------|-----------------|-------|
| WhatsApp Cloud API | 1,000 conversations/month | $0 | Family use stays within free tier |
| Gemini 2.5 Flash (extraction) | 1,500 req/day free | $0 | Claim extraction + translation |
| Gemini 2.5 Pro (verdict) | 1,500 req/day free | $0 | Verdict reasoning + video/audio |
| OpenAI fallback calls | Pay per token | Variable | Used only for controlled fallback/escalation paths |
| Tavily API | 1,000 credits/month free | 1 credit/basic search | ~2 searches per claim (L2+L3) |
| Google Fact Check API | Free | $0 | Always free |
| Google Cloud Vision (OCR) | 1,000 images/month free | $0 | Stays within free tier |
| Railway hosting | $5/month starter | $5 | Fixed cost |

**With all-Gemini + $5 OpenAI backup**: ~25 users at 2-3 checks/day, $0-5/month total.

---

## API Keys Required

```env
# WhatsApp Cloud API
WHATSAPP_ACCESS_TOKEN=<paste_token>
WHATSAPP_PHONE_NUMBER_ID=<paste_id>
WHATSAPP_BUSINESS_ACCOUNT_ID=<paste_id>
META_APP_SECRET=<paste_secret>
WHATSAPP_VERIFY_TOKEN=<any_random_string_you_choose>

# Gemini (primary LLM — get from https://aistudio.google.com/apikey)
GEMINI_API_KEY=<paste_key>

# OpenAI (fallback provider — $5 credit cap)
OPENAI_API_KEY=<paste_key>

# Tavily (web search for Layers 2, 3)
TAVILY_API_KEY=<paste_key>

# Google Cloud (Fact Check API + Vision OCR)
GOOGLE_API_KEY=<paste_key>
```

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

# 4. Install ffmpeg (for video processing fallback)
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
google-genai==1.69.0
pydantic==2.11.1
python-multipart==0.0.20
aiosqlite==0.21.0
youtube-transcript-api==1.0.3
yt-dlp==2026.3.17
```

---

## Future Roadmap (Not Started)

| Feature | Effort | Priority | Notes |
|---------|--------|----------|-------|
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
