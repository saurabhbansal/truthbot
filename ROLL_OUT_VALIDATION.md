# Rollout Validation and Monitoring

## Objective

Validate TruthBot performance, quality, and cost for a friends/family rollout (20-30 users) under a strict OpenAI budget cap.

## Pre-Launch Checklist

- Verify all content types work end-to-end:
  - text
  - image
  - image + caption
  - video upload
  - video + caption
  - video link
  - audio/voice
  - article link
- Verify feedback flow:
  - Helpful
  - Not Helpful -> reason picker
  - feedback revision behavior
- Verify endpoints:
  - `/stats`
  - `/feedback-stats`
  - `/admin/feedback`
  - `/runtime-metrics`

## Gemini Quota Matrix Execution (Phase 1 First)

1. In Google Cloud Console, select the same project backing `GEMINI_API_KEY`.
2. Enable billing for that project.
3. Ensure Gemini/Generative Language API is enabled.
4. Request/confirm Phase 1 quotas:
   - `gemini-2.5-flash`: `40 RPM`, `400,000 TPM`
   - `gemini-2.5-pro`: `12 RPM`, `180,000 TPM`
5. Set billing budget alert to `$10/month` with 50/80/100% alerts.
6. Verify post-change logs:
   - `429 RESOURCE_EXHAUSTED` materially reduced
   - no `limit: 0` quota messages for Pro
   - text/image/video-link checks complete without quota aborts
7. Escalate to Phase 2 only if 429s persist for 48-72h:
   - `gemini-2.5-flash`: `80 RPM`, `800,000 TPM`
   - `gemini-2.5-pro`: `24 RPM`, `360,000 TPM`

## Mixed-Traffic Budget Simulation

Use this baseline profile before launch:

- users: 25
- checks per user per day: 2
- monthly checks: ~1500
- mix:
  - image: 40%
  - video/video-link: 35%
  - text/article/audio: 25%

### Budget rule

- OpenAI monthly cap: `$5`
- Trigger warning if projected monthly spend exceeds `$4`
- Trigger emergency mode if spend exceeds `$5`

## Baseline Benchmark Pack (Required Before Canary)

Build and keep a fixed benchmark set with sample IDs so pre/post comparisons are objective:

- 10-15 text samples
- 10-15 image samples
- 10-15 video link samples
- 10 uploaded video samples
- 10 audio/voice samples
- 10 mixed-media samples

For each sample, record:
- expected top-level verdict style (decisive vs nuanced),
- expected claim relevance quality,
- expected source quality level,
- expected response conciseness (single-message target unless overflow needed).

## Two-Week Monitoring Plan

Track daily for first 14 days:

- Total checks
- Checks by type
- Fallback rate by type
- OpenAI requests/day
- Estimated OpenAI spend/day and cumulative
- Positive feedback rate
- Negative reason breakdown
- Wrong verdict trend

## Action Thresholds

- If OpenAI spend trend > $5/month:
  - tighten image escalation threshold first
  - review fallback trigger conditions
  - verify cache hit rate
- If negative feedback spikes:
  - inspect top negative reasons
  - inspect top repeated wrong-verdict claim hashes
  - run targeted prompt/source tuning

## Numeric Acceptance Gates (Go/No-Go)

- Text:
  - >=95% requests complete without hard failure
  - <=2% parse failures
  - >=80% benchmark samples rated actionable/relevant
- Image:
  - >=92% requests complete
  - <=3% parse/extraction failures
  - >=75% benchmark samples have non-noisy claim sets
- Video link:
  - >=85% end-to-end completion
  - <=5% parser failures
- Uploaded video/audio:
  - >=88% completion
  - <=5% hard failures
  - <=10% low-confidence-only responses
- Mixed media:
  - >=85% completion
  - coherent verdict-first formatting
- Cross-cutting:
  - fallback success >=90% when primary fails
  - post-quota 429 rate <2% of model calls in pilot window

## Weekly Review

- Review top recurring wrong-verdict clusters
- Review top problematic domains/sources
- Apply retrieval weight adjustments
- Re-test affected scenarios with regression examples

## Canary Rollout Sequence

1. Deploy to production with runtime metrics endpoint enabled.
2. Run smoke checks in this order:
   - text -> image -> video link -> uploaded video -> audio -> mixed media
3. Keep rollout to canary users only for 48h.
4. Track `/runtime-metrics`, `/stats`, `/feedback-stats` every 6h.
   - Optional helper: `python3 scripts/stabilization_gate_check.py --base-url "https://<your-service-url>"`
5. Expand to full friends/family cohort only if acceptance gates pass.
