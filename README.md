# TruthBot — WhatsApp Fact Checker

TruthBot helps family and friends verify forwarded text, images, videos, audio, and links on WhatsApp.

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

## Deployment

Configured for Railway deployment via Dockerfile.

## License

Private project.
