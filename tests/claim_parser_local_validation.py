from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("WHATSAPP_ACCESS_TOKEN", "local")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "local")
os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", "local")
os.environ.setdefault("OPENAI_API_KEY", "local")
os.environ.setdefault("GEMINI_API_KEY", "local")
os.environ.setdefault("TAVILY_API_KEY", "local")
os.environ.setdefault("GOOGLE_API_KEY", "local")

from app.engines.claim_extractor import _parse_claims_payload


CASES = [
    (
        "strict_json",
        '{"claims": ["WHO recommends 150 minutes weekly.", "HIIT improves insulin sensitivity."]}',
        2,
    ),
    (
        "fenced_json",
        "```json\n{\"claims\": [\"RBI raised repo rate to 8%.\"]}\n```",
        1,
    ),
    (
        "python_literal_like",
        "{'claims': ['भारत में ट्रैफिक 168 घंटे/वर्ष बेंगलुरु में बताया गया है।']}",
        1,
    ),
    (
        "quoted_non_json",
        'claims -> "Traffic is 104 hrs/year in Delhi" and "Traffic is 168 hrs/year in Bengaluru"',
        2,
    ),
    (
        "bullet_text",
        "- WHO recommends 150 minutes per week minimum\n- Exercise is best therapy for glycemic control",
        2,
    ),
    (
        "no_claims",
        "No verifiable claims found.",
        0,
    ),
]


def main() -> int:
    failures = []
    for name, payload, expected_min in CASES:
        claims = _parse_claims_payload(payload)
        if len(claims) < expected_min:
            failures.append((name, expected_min, len(claims), claims))
        print(f"{name}: extracted={len(claims)} -> {claims[:3]}")

    if failures:
        print("\nFAILURES:")
        for name, expected_min, got, claims in failures:
            print(f"- {name}: expected >= {expected_min}, got {got}, claims={claims}")
        return 1

    print("\nAll parser validation cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
