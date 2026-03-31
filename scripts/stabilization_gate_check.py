from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def metric_value(metrics: dict, contains: str) -> int:
    total = 0
    for key, value in metrics.items():
        if contains in key:
            total += int(value)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="TruthBot stabilization gate checker")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    runtime = fetch_json(f"{base}/runtime-metrics").get("metrics", {})
    stats = fetch_json(f"{base}/stats")
    feedback = fetch_json(f"{base}/feedback-stats")

    parse_failures = metric_value(runtime, "claim_extraction_failure|") + metric_value(
        runtime, "category=parse"
    )
    quota_failures = metric_value(runtime, "category=quota")
    fallback_success = metric_value(runtime, "verdict_fallback_success")
    video_link_failures = metric_value(runtime, "video_link_failure")

    print("=== Stabilization Gate Snapshot ===")
    print(f"base_url: {base}")
    print(f"total_checks: {stats.get('total_checks', 0)}")
    print(f"positive_feedback_rate_pct: {feedback.get('positive_rate_pct', 0.0)}")
    print(f"parse_failures: {parse_failures}")
    print(f"quota_failures: {quota_failures}")
    print(f"fallback_success: {fallback_success}")
    print(f"video_link_failures: {video_link_failures}")

    gate_failures: list[str] = []
    if quota_failures > 0:
        gate_failures.append("quota_failures>0")
    if parse_failures > 3:
        gate_failures.append("parse_failures>3")

    if gate_failures:
        print("gate_status: FAIL")
        print("reasons: " + ", ".join(gate_failures))
        return 1

    print("gate_status: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print(f"Failed to reach API: {exc}")
        raise SystemExit(2)
