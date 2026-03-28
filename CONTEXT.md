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

## Anti-Hallucination Pipeline (4 Steps)

This prevents the LLM from making things up:

1. **Search FIRST, reason SECOND** — The LLM never generates a verdict from its own knowledge. It first searches all 4 source layers, then synthesizes a verdict from the retrieved evidence only.
2. **Mandatory citation** — Every factual statement in the verdict must cite a specific source from the search results. If the LLM can't cite a source, it must say "I couldn't verify."
3. **Source validation** — Only sources actually returned by the search APIs are allowed. The LLM cannot "remember" URLs from training data.
4. **Confidence calibration** — Final confidence = 40% LLM self-assessed + 60% source-layer confidence. This prevents overconfident LLM outputs when sources are weak.

### Circular Misinformation Defense
When the same false claim gets copy-pasted across dozens of low-quality sites:
- **Source deduplication**: If 10 sites have identical text, treated as 1 source, not 10
- **Absence-of-authority detection**: If a claim is "confirmed" by 50 blogs but ZERO established news outlets or official sources covered it, TruthBot flags this
- **Layer 4 never cited**: General web results provide context only, never used as evidence in verdicts

---

## India-Specific Source Priorities

Since the primary audience is Indian family groups, these sources are prioritized:

| Category | Sources |
|----------|---------|
| Government fact-check | PIB Fact Check (pibfactcheck.in) — official government fact-check arm |
| Indian fact-checkers | BOOM Live, Alt News, Factly, Newschecker, The Quint (all IFCN-certified) |
| Government policy | pib.gov.in, india.gov.in, mha.gov.in |
| Financial | rbi.org.in, sebi.gov.in, incometaxindia.gov.in, gst.gov.in |
| Health | icmr.gov.in, mohfw.gov.in, aiims.edu |
| Science/Space | isro.gov.in, dst.gov.in |
| Weather/Disaster | imd.gov.in |
| Indian news | NDTV, The Hindu, Indian Express, Hindustan Times, The Wire, Scroll.in, LiveMint |

---

## Database Schema (SQLite)

Three tables:

```sql
-- Verdict caching (24h TTL, hash-based dedup)
cache: content_hash (PK), verdict_json, created_at

-- User feedback on verdicts
feedback: id, verdict_id, user_phone_hash, feedback_type, negative_reason,
          source_link, source_quality, free_text, created_at

-- Usage tracking
usage_stats: id, user_phone_hash, message_type, verdict_label,
             confidence, processing_ms, created_at
```

Phone numbers are never stored — only SHA-256 hashes (first 16 chars).

---

## Feedback Validation (Phase 2 Design — Not Built Yet)

For MVP, all feedback is logged as-is. Phase 2 adds a 5-signal validation system to handle spite feedback and improve accuracy:

1. **Source quality** — If user provides a correction link, check if it's from Layer 1-3 (credible) or Layer 4 (general web)
2. **Consensus** — If 3 users say "wrong" on the same verdict, that's strong signal
3. **User track record** — Users whose past feedback was validated get higher weight
4. **Category patterns** — If TruthBot keeps getting "wrong" feedback on health claims, the health prompts need tuning
5. **Recency** — Recent feedback weighted higher than old feedback

---

## WhatsApp API Notes

- **Forwarded vs uploaded content**: WhatsApp API treats them identically. The only difference is a `forwarded: true` metadata flag (and sometimes `frequently_forwarded: true` for viral content)
- **Frequently forwarded flag**: Useful signal — a frequently forwarded message is more likely to be viral misinformation
- **Temporary vs permanent token**: Temporary tokens expire in 24 hours. For production, need a System User token (see WhatsApp setup Part C)
- **Free tier**: 1,000 conversations/month free (a "conversation" is a 24-hour window with one user)
- **Media download**: Images/videos must be downloaded via a 2-step process (get media URL → download bytes)

---

## Test Results (Validated Claims)

These claims were tested and produced correct results:

| Claim | Expected | Actual | Status |
|-------|----------|--------|--------|
| "Drinking warm water with lemon cures cancer" | FALSE | FALSE (with fact-checker sources) | PASS |
| "India is the most populated country with 3B people" | Partial (TRUE + FALSE) | TRUE + FALSE (1.4B not 3B) | PASS |
| "Earth revolves around Sun in 365.25 days" | TRUE | TRUE | PASS |
| "URGENT: RBI banning 500 rupee notes from April 1" | FALSE | FALSE (with RBI sources) | PASS |
| "Demonetization happened today" | FALSE | FALSE (after prompt fix) | PASS |
| "WhatsApp charging Rs 5 per message" | FALSE | FALSE (after prompt fix) | PASS |
| "Modi announced free electricity for all" | FALSE | FALSE (with PIB sources) | PASS |
| "Congress ruled India for 60 years and did nothing" | FALSE | FALSE (corrected to ~30 years) | PASS |
| "Elon Musk bought WhatsApp in 2026" | FALSE | FALSE | PASS |
| "Ginger water cures bloating" | FALSE | FALSE (with PubMed sources) | PASS |
| Snopes.com link | Fact-checker | Recognized as fact-checker | PASS |
| Infowars.com link | Blocked | Blocked with warning | PASS |
| NDTV.com link | News outlet | Article extracted + fact-checked | PASS |
| The Hindu link | News outlet | Article extracted + fact-checked | PASS |

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

### 9. Broad Sensitive Generalizations Are Not Fact-Checked
**Problem**: Claims like "Muslims are dangerous" or "Hindus are under attack" are not verifiable factual claims — fact-checking them could legitimize hate speech.
**Decision**: TruthBot detects broad communal/religious generalizations and responds with a neutral redirect asking for a specific incident instead. This avoids taking sides while still being helpful.
**File**: `app/engines/text_handler.py` — see `_is_broad_sensitive_generalization()`

### 10. Claims Are Grounded Before Fact-Checking
**Problem**: The LLM claim extractor could hallucinate claims not present in the original text.
**Decision**: After extraction, claims are filtered through `filter_grounded_claims()` which checks token overlap against the source text. Only claims with 85%+ token overlap are kept.
**File**: `app/engines/claim_extractor.py`

### 11. Non-English Claims Are Translated Before Searching
**Problem**: Hindi/regional language claims searched against English sources returned poor results.
**Decision**: Claims are auto-translated to English before source searching, while preserving names, numbers, and dates exactly. The original claim language is preserved in the user-facing output.
**File**: `app/engines/claim_extractor.py` — see `translate_claim_to_english()`

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

## File Structure

```
truthbot/
├── app/
│   ├── main.py                    # FastAPI app, health + stats + legal policy endpoints
│   ├── config.py                  # Environment variables loader
│   ├── router/
│   │   └── content_router.py      # Message dispatcher (text/image/video/link/feedback)
│   ├── engines/
│   │   ├── claim_extractor.py     # LLM claim extraction + translation + grounding filter
│   │   ├── verdict_engine.py      # Core verdict logic + anti-hallucination prompt
│   │   ├── text_handler.py        # Full text fact-check pipeline + sensitive content guard
│   │   ├── image_handler.py       # OCR + AI detection + text pipeline
│   │   ├── video_handler.py       # Hive deepfake + caption pipeline
│   │   ├── link_handler.py        # Domain classification + article extraction + social cleanup
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
├── test_cli.py                    # Interactive CLI test harness (text, textfile, link, image, video)
├── test_webhook.py                # Webhook payload simulator
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Docker containerization
├── Procfile                       # Railway process file
├── railway.toml                   # Railway config
├── GUIDE.md                       # "How to Use TruthBot" guide for family
├── README.md                      # Quick start + architecture overview
├── PRIVACY_POLICY.md              # Privacy policy (for Meta app review)
├── TERMS_OF_SERVICE.md            # Terms of service (for Meta app review)
├── DATA_DELETION.md               # Data deletion instructions (for Meta app review)
└── .env.example                   # API key template
```

---

## 5 Partial-Truth Patterns (Critical for Verdict Quality)

These are the most important scenarios TruthBot handles. Outright false is easy -- partial truths are what slip through family groups.

| Pattern | Label | What's Happening | Example |
|---------|-------|-----------------|---------|
| **A** | MISLEADING | True fact + false conclusion drawn from it | "Harvard study proves turmeric kills cancer cells. Stop chemo and use turmeric!" (study is real, conclusion is dangerous) |
| **B** | MOSTLY FALSE | Right topic, wrong numbers/details exaggerated | "India's GDP grew 15% this quarter!" (real growth is ~6.5%) |
| **C** | OUTDATED | Was true before, no longer current | "WHO declares COVID global health emergency!" (ended May 2023) |
| **D** | MISSING CONTEXT | True stats but framed to mislead | "Crime rate up 200% in City X!" (because new online reporting system launched, not more crime) |
| **E** | OUT OF CONTEXT | Real media, fake caption/wrong attribution | Real flood photo from Bangladesh 2024 captioned "Terrible floods in Chennai today!" |

For every partial-truth verdict, TruthBot always shows both sides: "What's TRUE" and "What's FALSE/WRONG/MISSING" — this builds trust because users see TruthBot acknowledges the true parts.

---

## All UI Scenarios

| # | Scenario | Content Type | MVP? | What TruthBot Does |
|---|----------|-------------|------|-------------------|
| 1 | User sends "hi"/"hello"/"namaste" | Text | Yes | Onboarding message with instructions |
| 2 | User sends "help" | Text | Yes | Tips and usage guide |
| 3 | User forwards a text claim | Text | Yes | Claim extraction → 4-layer search → verdict |
| 4 | User forwards text with URL | Text+Link | Yes | Domain classification → article extraction → fact-check |
| 5 | User forwards an image | Image | Yes | OCR + AI detection (Hive) + text pipeline |
| 6 | User forwards a video | Video | Yes | Hive deepfake detection + caption pipeline |
| 7 | User sends audio/voice note | Audio | No | "Coming soon" message with suggestion to type the claim |
| 8 | User sends a document | Document | No | "Can't check documents yet" message |
| 9 | User sends sticker/contact/location | Other | No | "Can't check those" message |
| 10 | User sends random conversational text | Text | Yes | Redirect to fact-checking purpose |
| 11 | Verdict has multiple claims | Text | Yes | Multi-claim format with per-claim verdicts |
| 12 | Verdict is partial truth | Text | Yes | "What's TRUE vs What's WRONG" breakdown |
| 13 | User uploads image from device | Image | Yes | Same as forwarded image (WhatsApp API treats identically) |
| 14 | User uploads video from device | Video | Yes | Same as forwarded video |
| 15 | Image with caption | Image+Text | Yes | AI detection + OCR + caption fact-check combined |
| 16 | Video with caption | Video+Text | Yes | Deepfake detection + caption fact-check combined |
| 17 | Feedback: user taps "Helpful" | Interactive | Yes | Thank you + log positive feedback |
| 18 | Feedback: user taps "Not Helpful" | Interactive | Yes | Follow-up reason list → log |
| 19 | Feedback: user taps "Wrong" | Interactive | Yes | Ask for correct source link → log |
| 20 | Rate limited user | Any | Yes | "Slow down" message (5 req/min) |

---

## Cost Estimate (Monthly, for ~50 users)

| Service | Free Tier | Estimated Monthly Cost |
|---------|-----------|----------------------|
| WhatsApp Cloud API | 1,000 conversations/month free | $0 (family use stays within free tier) |
| OpenAI GPT-4o-mini | Pay per token | ~$2-5 (claim extraction + verdict reasoning) |
| Tavily API | 1,000 searches/month free | $0-5 (depends on usage) |
| Google Fact Check API | Free | $0 |
| Google Cloud Vision (OCR) | 1,000 images/month free | $0 |
| Hive Moderation | Free credits on signup | $0-3 (depends on image/video volume) |
| Railway hosting | $5/month starter | $5 |
| **Total** | | **~$7-18/month** |

---

## WhatsApp Cloud API Setup (Step-by-Step)

This is the detailed guide for when the spare phone number is available.

### PART A: Meta Account & Developer App (done)
- Meta Business portfolio "Fact Fury" created
- Developer app "TruthBot" created at developers.facebook.com
- WhatsApp product added to the app
- Test phone number available: +1 555 155 4793
- Phone Number ID: 104422784189684400
- Business Account ID: 206118288133354

### PART B: Register Spare Phone Number (PENDING — blocker)
1. Go to Meta Developer Console → Your App → WhatsApp → API Setup
2. Click "Add phone number"
3. Enter the spare phone number (must NOT be registered on WhatsApp already)
4. Choose verification method: SMS or Voice call
5. Enter the OTP received on the spare SIM
6. Once verified, the phone number becomes TruthBot's number

### PART C: Generate Permanent Access Token
1. Go to Meta Developer Console → Your App → WhatsApp → API Setup
2. The temporary token (24h) is already generated
3. For a permanent token: Business Settings → System Users → Create system user → Generate token with `whatsapp_business_messaging` permission
4. Update `.env` with the permanent token

### PART D: Deploy to Railway
1. Go to railway.app and connect your GitHub repo
2. Railway auto-detects the Dockerfile
3. Set all environment variables from `.env` in Railway's dashboard
4. Deploy — Railway gives you a URL like `https://truthbot-production-xxxx.up.railway.app`

### PART E: Set Webhook URL
1. Go to Meta Developer Console → Your App → WhatsApp → Configuration
2. Set Webhook URL: `https://<railway-url>/webhook`
3. Set Verify Token: same value as `WHATSAPP_VERIFY_TOKEN` in `.env`
4. Subscribe to messages: check `messages` field
5. Meta will send a GET request to verify — the server must be running

### PART F: Test End-to-End
1. Send "hi" from your personal WhatsApp to TruthBot's number
2. You should get the onboarding message back
3. Forward a suspicious message — you should get a verdict
4. If it works, share TruthBot's number with family

---

## Rollout Strategy

### Phase 1: Personal Testing (you only)
- Test all content types: text, image, video, link
- Test edge cases: Hindi text, very long messages, multiple URLs
- Test error handling: send unsupported content, rapid-fire messages

### Phase 2: Inner Circle (3-5 trusted people)
- Share with tech-savvy family members who can give good feedback
- Monitor logs and feedback database
- Tune prompts based on real-world claims

### Phase 3: Family Rollout (10-30 people)
- Share the GUIDE.md instructions
- Share TruthBot's number in family groups
- Message: "Hey everyone, I built a bot that checks if forwarded messages are real or fake. Save this number and forward anything suspicious to it!"
- Monitor usage stats via `/stats` endpoint

### Phase 4: Iterate
- Review feedback weekly
- Add Hindi responses if family requests it
- Expand allowlists based on Indian sources that come up frequently
- Tune prompts based on patterns in wrong verdicts

---

## Future Roadmap (Not Started)

| Feature | Effort | Priority | Notes |
|---------|--------|----------|-------|
| Hindi responses | Low | High | LLMs generate Hindi natively; just add language detection + prompt tweak |
| Audio/voice note checking | Medium | Medium | Need speech-to-text (Whisper API) → then route through text pipeline |
| Group chat @mention | High | Low | Requires WhatsApp Business API group features; complex permissions |
| Reverse image search | Medium | Medium | Google Lens API or TinEye for out-of-context image detection |
| Automated bias testing | Medium | Medium | Run same claim from both political sides, compare tone/harshness |
| Advanced feedback validation | Medium | Low | Consensus scoring, user track record, category patterns |
| Multi-language support | Low per language | Low | Add language detection, translate claims, respond in detected language |
| Admin dashboard | Medium | Low | Web UI showing usage stats, feedback trends, verdict distribution |

---

## Acknowledgment Messages (UX Flow)

TruthBot sends an immediate acknowledgment before processing, so users know it's working:

| Content Type | Acknowledgment |
|-------------|---------------|
| Text | "Got it! Checking this now... ⏳ (usually takes 5-10 seconds)" |
| Image | "Got your image! Analyzing it... 🔍 (this may take 10-15 seconds)" |
| Video | "Got your video! This takes a bit longer to analyze — I'll get back to you in about 30-60 seconds. Hang tight! ⏳" |
| Link | "Got the link! Let me check the article and the source... 🔍" |

Errors get a friendly "Oops, something went wrong..." message (never stack traces).

---

## Sensationalist Language Detection

TruthBot flags content with sensationalist patterns (defined in `app/sources/allowlists.py`):
"SHOCKING", "They don't want you to know", "EXPOSED", "BREAKING", "Share before deleted", "Forward to everyone", "Urgent!!!", "100% proven", "Doctors hate this", "Big pharma", "Government hiding", "Wake up people", "BANNED"

These patterns are used as signals for low credibility, not as automatic verdicts.

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
```

---

## Configuration Details (app/config.py)

- **LLM model**: `gpt-4o-mini` by default (configurable via `OPENAI_MODEL` env var)
- **WhatsApp API version**: v22.0
- **Database**: SQLite file at `truthbot.db` (configurable via `DATABASE_PATH`)
- **Hive API key**: Optional — if not set, AI detection is skipped gracefully
- **META_APP_SECRET**: Optional — used for webhook signature verification (recommended for production)
- **WHATSAPP_BUSINESS_ACCOUNT_ID**: Optional — only needed for some API calls

---

## Recent Enhancements (added from personal machine)

These were added after the initial 8 phases were completed:

### 1. Meta App Review — Legal Policy Endpoints
Three hosted HTML endpoints added to `app/main.py` for Meta's app publishing requirements:
- `/privacy-policy` — Privacy policy page
- `/terms` — Terms of service page
- `/data-deletion` — Data deletion instructions
- Corresponding markdown files: `PRIVACY_POLICY.md`, `TERMS_OF_SERVICE.md`, `DATA_DELETION.md`
- Contact email: `factfuryteam@gmail.com`

### 2. Multilingual Claim Support
- **Claim translation**: Non-English claims (Hindi, etc.) are now auto-translated to English before searching sources (`translate_claim_to_english` in `claim_extractor.py`)
- **Max claims increased**: From 5 to 12 per message, with max_tokens increased to 1000
- **Grounding filter**: New `filter_grounded_claims()` function ensures extracted claims are actually present in the source text (prevents LLM hallucinating claims)

### 3. Broad Sensitive Generalization Guard
- `text_handler.py` now detects broad communal/religious generalizations (e.g., "Muslims are dangerous", "Hindus are under attack")
- Instead of fact-checking these (which could legitimize hate speech), TruthBot responds: "This statement is too broad to verify. Please share a specific incident with details."
- Covers group terms (Hindu, Muslim, Christian, Sikh, Dalit, Brahmin) + generalization terms (under attack, are dangerous, want to destroy, etc.)

### 4. Social Media Link Cleanup
- `link_handler.py` now has special handling for social media domains (Facebook, Instagram, X/Twitter, TikTok)
- `_clean_extracted_content()` strips markdown images, base64 blobs, SVG markup, and UI scaffolding
- `_extract_social_post_text()` extracts just the post text, stopping before comments/reactions/UI noise

### 5. Multi-claim Display Fix
- `formatter.py`: Removed the 80-char truncation on claim text in multi-verdict output — full claims now shown

### 6. CLI `textfile` Command
- `test_cli.py` now supports `textfile <path>` to load and fact-check text from a file (useful for long WhatsApp forwards)

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
- [x] Phase 9: Meta app review (legal policies, hosted endpoints)
- [x] Phase 9b: Multilingual claims, grounding filter, sensitive content guard, social link cleanup

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
