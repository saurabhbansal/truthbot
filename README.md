# TruthBot — WhatsApp Fact Checker

A WhatsApp bot that helps family and friends verify forwarded messages, images, videos, and links. Forward anything suspicious to TruthBot and get a clear verdict: TRUE, FALSE, MISLEADING, or one of several nuanced labels.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/saurabhbansal/truthbot.git
cd truthbot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env template and fill in your API keys
cp .env.example .env
# Edit .env with your actual keys

# Run locally
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000` to verify the health check.

## Architecture

```
WhatsApp User → WhatsApp Cloud API → Webhook (FastAPI) → Content Router
                                                              ↓
                                          ┌─────────────────────────────────┐
                                          │  Text Engine  │  Image Engine   │
                                          │  Link Engine  │  Video Engine   │
                                          └─────────────────────────────────┘
                                                              ↓
                                                    4-Layer Source Trust
                                                    (Fact-Check DBs →
                                                     Official Sources →
                                                     News Outlets →
                                                     Web Search)
                                                              ↓
                                                     Verdict Composer
                                                              ↓
                                                WhatsApp Cloud API → User
```

## API Keys Required

| Service | Purpose | Get it at |
|---------|---------|-----------|
| WhatsApp Cloud API | Send/receive messages | developers.facebook.com |
| OpenAI | Claim extraction, reasoning | platform.openai.com |
| Tavily | Web search for verification | app.tavily.com |
| Google Cloud | Fact Check API + Vision OCR | console.cloud.google.com |
| Hive Moderation | AI image/video + deepfake detection | thehive.ai |

## Deployment

Configured for Railway deployment via Dockerfile. Push to `main` branch to auto-deploy.

## License

Private project.
