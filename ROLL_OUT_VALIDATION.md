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

## Weekly Review

- Review top recurring wrong-verdict clusters
- Review top problematic domains/sources
- Apply retrieval weight adjustments
- Re-test affected scenarios with regression examples
