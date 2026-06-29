# TruthBot — WhatsApp Fact Checker

TruthBot helps family and friends verify forwarded text, images, videos, audio, and links on WhatsApp.

## 30-Second Project Highlights

- Built an end-to-end AI backend product from webhook ingestion to user-facing verdict delivery on WhatsApp.
- Implemented multi-modal handling for text, links, images (OCR + AI detection), and videos (deepfake/AI checks).
- Designed a reliability-first evidence flow using layered sources and anti-hallucination constraints.
- Added production-minded safeguards: async FastAPI architecture, caching, rate limiting, feedback loop, and deploy-ready Docker setup.

## For Recruiters

- Built as an end-to-end AI product prototype: webhook ingestion, multimodal analysis, source retrieval, verdict synthesis, and WhatsApp response delivery.
- Focused on practical reliability: layered evidence sources, fallback model paths, and structured error handling.
- Demonstrates product-minded engineering: user feedback loop, metrics endpoints, and deployable containerized service.
- Security-first setup: secrets are environment-only (`.env`), with a placeholder-only `.env.example`.

## Demo

Add your best proof points here before sharing publicly:

- `docs/demo.gif` — 20-40 second end-to-end flow (forward message -> receive verdict)
- `docs/screenshot-chat.png` — WhatsApp-style verdict output example
- `docs/screenshot-arch.png` — architecture diagram

If you do not have media yet, remove this section or replace with a short "Live Demo available on request."

## Quick Start

```bash
git clone https://github.com/saurabhbansal/truthbot.git
cd truthbot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000` for health check.

## Current Model Architecture

- Claim extraction/translation: Gemini 2.5 Flash
- Verdict reasoning: Gemini 2.5 Pro (fallback: OpenAI GPT-5.4)
- Image analysis: Gemini-first with OpenAI fallback/escalation
- Video analysis: Gemini native video (fallback: ffmpeg + OpenAI vision + Whisper)
- Audio analysis: Gemini native audio (fallback: Whisper)
- Evidence: Google Fact Check + Tavily, with Gemini Grounding overflow fallback

## Feedback and Analytics

- 2-step feedback flow: Helpful / Not Helpful, then reason selection for negative feedback
- Feedback is revisable (latest feedback state wins)
- Dashboard endpoints:
  - `/stats`
  - `/feedback-stats`
  - `/admin/feedback`

## API Keys Required

- WhatsApp Cloud API
- Gemini API key
- OpenAI API key (fallback paths)
- Tavily API key
- Google API key (Fact Check + OCR)

## Security Note for Public Repo

- Never commit `.env` or live API keys.
- Rotate any key immediately if it is ever exposed locally or remotely.
- Use separate dev/test/prod credentials with least-privilege scopes.

## Deployment

Configured for Railway deployment via Dockerfile.

## License

Portfolio/demo project. All rights reserved unless explicitly licensed otherwise.
