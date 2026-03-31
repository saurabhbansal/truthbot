# Stabilization Smoke Checklist

## Automated checks executed

- `python3 -m compileall app` -> pass
- `python3 tests/mixed_traffic_budget_simulation.py` -> pass (`within_budget: True`)

## Manual production smoke checks (run in this order)

1. Text claim
2. Image
3. Image + caption
4. Video link (YouTube)
5. Video link (Instagram/Reels/TikTok/X)
6. Uploaded video
7. Audio/voice note
8. Mixed media (image + text / video + text)

For each check, verify:

- verdict-first format appears
- claim extraction is relevant (not noisy)
- response is concise (single message unless overflow is required)
- no "unsupported_parameter" error in logs
- no parser crash / traceback
- fallback path succeeds when primary fails

## Runtime metrics to inspect

- `/runtime-metrics`:
  - `claim_extraction_failure|...|category=parse`
  - `verdict_primary_failure|...|category=quota`
  - `verdict_fallback_success`
  - `video_link_failure`
- `/stats`
- `/feedback-stats`
