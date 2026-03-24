"""Simulate WhatsApp webhook payloads against the local server.

Sends fake webhook POST requests to test the full pipeline
without needing a real WhatsApp connection.

Usage:
    1. Start the server: uvicorn app.main:app --port 8000
    2. Run this: python test_webhook.py

The server will process the messages but WhatsApp send calls will fail
(no real phone number). Check the server logs to see the full pipeline execute.
"""

from __future__ import annotations

import httpx
import json
import sys

BASE_URL = "http://localhost:8000/webhook"

FAKE_SENDER = "919999999999"


def make_text_payload(text: str) -> dict:
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{"profile": {"name": "Test User"}}],
                    "messages": [{
                        "from": FAKE_SENDER,
                        "type": "text",
                        "text": {"body": text},
                    }],
                }
            }]
        }]
    }


def make_link_payload(url: str) -> dict:
    return make_text_payload(url)


TEST_CASES = [
    ("Greeting", make_text_payload("hi")),
    ("Help", make_text_payload("help")),
    ("False claim", make_text_payload("NASA confirmed an asteroid will hit Earth on April 15, 2026")),
    ("Health misinformation", make_text_payload("Drinking hot water with lemon cures cancer. WHO confirmed this.")),
    ("Partial truth", make_text_payload("India is the most populated country with 3 billion people")),
    ("True claim", make_text_payload("The Earth revolves around the Sun")),
    ("WhatsApp forward", make_text_payload(
        "URGENT!!! RBI announced all 500 rupee notes banned from April 1. "
        "Deposit your cash immediately!!! Forward to everyone!!!"
    )),
    ("Link check", make_link_payload("https://www.ndtv.com")),
    ("Blocked link", make_link_payload("https://infowars.com/fake-article")),
]


def main() -> None:
    print(f"\n{'=' * 60}")
    print("  TruthBot Webhook Simulator")
    print(f"{'=' * 60}")
    print(f"\nSending {len(TEST_CASES)} test payloads to {BASE_URL}")
    print("(WhatsApp replies will fail — check server logs for pipeline output)\n")

    # Check server is running
    try:
        r = httpx.get("http://localhost:8000/", timeout=5)
        print(f"Server status: {r.json()}\n")
    except Exception:
        print("ERROR: Server not running. Start it first:")
        print("  cd truthbot && source venv/bin/activate && uvicorn app.main:app --port 8000\n")
        sys.exit(1)

    for name, payload in TEST_CASES:
        print(f"  [{name}]... ", end="", flush=True)
        try:
            r = httpx.post(BASE_URL, json=payload, timeout=60)
            print(f"HTTP {r.status_code} — {r.json()}")
        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\nDone! Check server logs for detailed pipeline output.")
    print(f"Stats: http://localhost:8000/stats\n")


if __name__ == "__main__":
    main()
