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

---

## Architecture Overview

```
WhatsApp User
    │
    ▼
Meta WhatsApp Cloud API (webhook)
    │
    ▼
FastAPI Server (app/main.py)
    │
    ▼
Content Router (app/router/content_router.py)
    │
    ├── Text → Claim Extractor → 4-Layer Source Search → Verdict Engine → Formatter
    ├── Image → OCR (Google Vision) + AI Detection (Hive) + Text Pipeline
    ├── Video → Deepfake Detection (Hive) + Caption Pipeline
    ├── Link → Domain Classification + Article Extraction (Tavily) + Text Pipeline
    ├── Audio → "Coming soon" message
    └── Interactive → Feedback Handler
    │
    ▼
WhatsApp Reply (verdict + sources + feedback buttons)
```

---

## 4-Layer Source Trust Architecture

This is the backbone of TruthBot's credibility. Sources are searched in parallel and weighted by trust:

| Layer | Source | Trust Weight | What It Does |
|-------|--------|-------------|-------------|
| **L1** | Google Fact Check Tools API | 1.0 (highest) | Searches IFCN-certified fact-checkers (BOOM, Alt News, Snopes, AFP, etc.) |
| **L2** | Official Sources (Tavily) | 0.85 | Targeted search on .gov, .edu, RBI, WHO, PIB, ICMR, NASA, etc. |
| **L3** | News Outlets (Tavily) | 0.6 | Search filtered to curated allowlist (NDTV, The Hindu, Reuters, BBC, etc.) |
| **L4** | General Web (Tavily) | 0.2 | Context only — NEVER cited directly in verdicts. Blocked domains filtered out. |

Confidence scoring: base score from highest layer that returned results + bonus for multiple layers agreeing + bonus for multiple sources within a layer.

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

## Key Design Decisions (and WHY)

These decisions were made through iterative testing and discussion. Do NOT change them without good reason.

### 1. FALSE vs UNVERIFIED
**Problem**: The LLM was defaulting to UNVERIFIED for claims like "demonetization happened today" even when sources clearly showed no such event occurred.
**Decision**: For major public events (government policy, disasters, financial regulations, etc.), absence of coverage across official sources and news outlets IS strong evidence of falsehood. UNVERIFIED is ONLY for truly obscure/niche claims with zero related information.
**File**: `app/engines/verdict_engine.py` — see "CRITICAL RULE — When to use FALSE vs UNVERIFIED"

### 2. No Confidence Indicator Shown to Users
**Problem**: Showing 🟢/🟡/🔴 confidence dots confused non-technical users. "FALSE with Low confidence" made them doubt the verdict.
**Decision**: Confidence is baked into the TONE of the response instead:
- High confidence → direct language ("This is false.")
- Medium confidence → softer language + tip ("Check the sources below before sharing")
- Low confidence → cautious language + tip ("I found limited sources, take with a pinch of salt")
**File**: `app/verdict/formatter.py`

### 3. No Source Credibility Label for Links
**Problem**: Showing "Source credibility: medium-high" for links was meaningless to family users.
**Decision**: Removed credibility labels. Only blocked domains show a warning. Source credibility is already factored into the verdict via the 4-layer trust system.
**File**: `app/engines/link_handler.py`

### 4. Strict Neutrality
**Problem**: LLM could editorialize or show political bias.
**Decision**: 8 explicit neutrality rules in the verdict prompt. Never praise/criticize any government, party, leader, religion, or community. Same standard for all claims. No loaded words. Tested with politically sensitive claims from both sides.
**File**: `app/engines/verdict_engine.py` — see "NEUTRALITY RULES (MANDATORY)"

### 5. Anti-Hallucination Pipeline
**Decision**: Search first, reason second. LLM can ONLY cite sources from the evidence provided. Never invent URLs. If unsure, lower confidence rather than guess. Source confidence weighted 60% vs LLM self-assessed confidence 40%.
**File**: `app/engines/verdict_engine.py`

### 6. Claim Extraction Preserves Original Meaning
**Decision**: Claims are extracted exactly as stated — no reframing, no editorializing. Opinions ("Modi is the best PM") are skipped, but factual claims embedded in opinions ("Modi built 10M houses") are extracted.
**File**: `app/engines/claim_extractor.py`

### 7. Hive for AI/Deepfake Detection (both image AND video)
**Decision**: Hive Moderation API handles both image and video AI-generation detection + deepfake detection. GPT-4o is used for reasoning/verdict, not for detection.
**Files**: `app/engines/hive_detector.py`, `app/engines/image_handler.py`, `app/engines/video_handler.py`

### 8. Feedback on Every Verdict
**Decision**: Interactive WhatsApp buttons (Helpful / Not Helpful / Wrong) sent after every verdict. Negative feedback triggers a follow-up list (inaccurate, missing info, bad sources, unclear, other). "Wrong" feedback prompts user to share a correct source link.
**File**: `app/feedback/feedback_handler.py`

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Server | FastAPI + Uvicorn | Webhook server |
| LLM | OpenAI GPT-4o-mini | Claim extraction, verdict reasoning |
| Fact-Check DB | Google Fact Check Tools API | Layer 1 source |
| Web Search | Tavily API | Layers 2, 3, 4 + article extraction |
| OCR | Google Cloud Vision API | Text extraction from images |
| AI Detection | Hive Moderation API | AI-generated + deepfake detection (image & video) |
| Database | SQLite (aiosqlite) | Caching (24h TTL), feedback logging, usage stats |
| Messaging | WhatsApp Cloud API | Receive/send messages, media download |
| Deployment | Docker + Railway | Cloud hosting |
| Repo | github.com/saurabhbansal/truthbot | Private repo |

---

## File Structure (36 Python files, ~2,700 lines)

```
truthbot/
├── app/
│   ├── main.py                    # FastAPI app, health + stats endpoints
│   ├── config.py                  # Environment variables loader
│   ├── router/
│   │   └── content_router.py      # Message dispatcher (text/image/video/link/feedback)
│   ├── engines/
│   │   ├── claim_extractor.py     # LLM claim extraction from text
│   │   ├── verdict_engine.py      # Core verdict logic + anti-hallucination prompt
│   │   ├── text_handler.py        # Full text fact-check pipeline orchestrator
│   │   ├── image_handler.py       # OCR + AI detection + text pipeline
│   │   ├── video_handler.py       # Hive deepfake + caption pipeline
│   │   ├── link_handler.py        # Domain classification + article extraction
│   │   ├── ocr.py                 # Google Cloud Vision OCR
│   │   └── hive_detector.py       # Hive AI/deepfake detection
│   ├── sources/
│   │   ├── allowlists.py          # 50+ trusted domains, 14 blocked domains
│   │   ├── fact_check_db.py       # Layer 1: Google Fact Check API
│   │   ├── official_sources.py    # Layer 2: Official .gov/.edu search
│   │   ├── news_sources.py        # Layer 3: Curated news outlets
│   │   ├── web_search.py          # Layer 4: General web with blocklist
│   │   └── source_trust.py        # Aggregates all 4 layers, computes confidence
│   ├── verdict/
│   │   ├── confidence.py          # Verdict labels enum, confidence thresholds
│   │   └── formatter.py           # WhatsApp message formatting
│   ├── feedback/
│   │   └── feedback_handler.py    # Interactive buttons, follow-up, DB logging
│   ├── db/
│   │   ├── database.py            # SQLite init (cache, feedback, usage_stats tables)
│   │   ├── cache.py               # Hash-based verdict caching (24h TTL)
│   │   └── usage.py               # Usage statistics tracking
│   ├── whatsapp/
│   │   ├── webhook.py             # GET verify + POST receive + rate limiting
│   │   ├── sender.py              # Send text, buttons, lists to WhatsApp
│   │   └── media.py               # Download media from WhatsApp
│   └── utils/
│       ├── logger.py              # Logging utility
│       └── rate_limiter.py        # In-memory rate limiter (5 req/min per phone)
├── test_cli.py                    # Interactive CLI test harness
├── test_webhook.py                # Webhook payload simulator
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Docker containerization
├── Procfile                       # Railway process file
├── railway.toml                   # Railway config
├── GUIDE.md                       # "How to Use TruthBot" guide for family
├── README.md                      # Quick start + architecture overview
└── .env.example                   # API key template
```

---

## What's Built (Complete)

- [x] Phase 0: Project structure, FastAPI skeleton, Dockerfile, GitHub repo
- [x] Phase 1: WhatsApp webhook, sender, media download, content router, onboarding/help
- [x] Phase 2: 4-layer source trust (Fact Check API, official, news, web, allowlists)
- [x] Phase 3: Text engine (claim extraction, anti-hallucination, verdict composer, all 9 labels)
- [x] Phase 4: Image engine (OCR + Hive AI detection + text pipeline)
- [x] Phase 4b: Video engine (Hive deepfake detection + caption pipeline)
- [x] Phase 5: Link engine (domain classification, article extraction, text pipeline)
- [x] Phase 5b: Feedback mechanism (buttons, follow-up, DB logging)
- [x] Phase 6: Caching, rate limiting, usage stats, error handling
- [x] Phase 7: Testing + prompt tuning (claim extractor, verdict engine, formatter)
- [x] Phase 8: "How to Use TruthBot" guide (GUIDE.md)

---

## What's Pending

### To Go Live on WhatsApp:
1. **Get a spare phone number** — register it in Meta Business Manager
2. **Generate a permanent WhatsApp access token** (the temporary one expires in 24h)
3. **Deploy to Railway** — `railway up` (Dockerfile is ready)
4. **Set webhook URL** in Meta Developer Console → `https://<railway-url>/webhook`
5. **Test with real WhatsApp messages**

### Future Enhancements (not started):
- Hindi responses (Phase 1.5)
- Audio/voice note fact-checking
- Group chat @mention support
- Automated bias testing (same claim from both political sides)
- User-reported bias feedback button
- Reverse image search
- Advanced feedback validation (consensus, user track record)

---

## Prompt Tuning History

These are the specific prompt issues found and fixed during testing. Important context for future tuning.

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Claims not extracted from health messages | `response_format: json_object` requires JSON object, but prompt asked for array | Changed prompt to request `{"claims": [...]}` format |
| "Demonetization happened today" → UNVERIFIED | Prompt said "if insufficient evidence, MUST be UNVERIFIED" | Added rule: for major events, absence of coverage = FALSE |
| "WhatsApp charging Rs 5" → UNVERIFIED | Same over-cautious default | Same fix as above |
| Confidence indicator confused users | 🟢/🟡/🔴 dots were technical noise | Removed indicator, baked confidence into response tone |
| Summaries too generic ("This is false") | Summary instruction didn't ask for specifics | Added examples: "India's population is 1.4B, not 3B" |
| Source credibility label on links | "medium-high" meaningless to family | Removed for all links except blocked domains |
| Potential political bias | No explicit neutrality rules | Added 8 neutrality rules + tested with claims from both sides |
| "Misinformation" is a loaded word | Used in hardcoded image/video/link messages | Replaced with neutral alternatives |

---

## API Keys Required

The following API keys are needed. When setting up on a new machine, create a `.env` file in the project root with these values:

```env
# WhatsApp Cloud API
# Get from: Meta Developer Console → Your App → WhatsApp → API Setup
WHATSAPP_ACCESS_TOKEN=<paste_token>
WHATSAPP_PHONE_NUMBER_ID=<paste_id>
WHATSAPP_BUSINESS_ACCOUNT_ID=<paste_id>
META_APP_SECRET=<paste_secret>
WHATSAPP_VERIFY_TOKEN=<any_random_string_you_choose>

# OpenAI
# Get from: https://platform.openai.com/api-keys
OPENAI_API_KEY=<paste_key>

# Tavily (web search for Layers 2, 3, 4)
# Get from: https://tavily.com → Dashboard → API Keys
TAVILY_API_KEY=<paste_key>

# Google Cloud (Fact Check API + Vision OCR)
# Get from: https://console.cloud.google.com → APIs & Services → Credentials
# Enable: Fact Check Tools API + Cloud Vision API
GOOGLE_API_KEY=<paste_key>

# Hive Moderation (AI image + video detection + deepfake)
# Get from: https://thehive.ai → Dashboard → API Keys
HIVE_API_KEY=<paste_key>
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

# 4. Create .env file (Cursor agent should create this and ask for keys)

# 5. Test locally
python test_cli.py

# 6. Run the server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## How to Test (Without WhatsApp Phone Number)

### CLI Test Harness (interactive)
```bash
python test_cli.py
```
Then type any claim, `link <url>`, `image <path>`, `video <path>`, `hi`, `help`, `stats`, `quit`.

### Webhook Simulator (automated)
```bash
# Terminal 1: Start server
uvicorn app.main:app --port 8000

# Terminal 2: Fire test payloads
python test_webhook.py
```

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
