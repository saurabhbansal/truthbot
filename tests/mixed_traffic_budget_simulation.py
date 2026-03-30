from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TrafficProfile:
    users: int = 25
    checks_per_user_per_day: float = 2.0
    image_share: float = 0.40
    video_share: float = 0.35
    text_audio_article_share: float = 0.25


@dataclass
class CostProfile:
    openai_budget_usd: float = 5.0
    days: int = 30
    verdict_fallback_rate: float = 0.08
    image_fallback_rate: float = 0.15
    video_fallback_rate: float = 0.10
    verdict_fallback_cost: float = 0.020  # GPT-5.4
    image_fallback_cost: float = 0.025  # GPT-4o fallback default
    video_fallback_cost: float = 0.0032


def simulate(traffic: TrafficProfile, costs: CostProfile) -> dict:
    checks_per_day = traffic.users * traffic.checks_per_user_per_day
    monthly_checks = checks_per_day * costs.days

    image_checks = monthly_checks * traffic.image_share
    video_checks = monthly_checks * traffic.video_share
    text_audio_article_checks = monthly_checks * traffic.text_audio_article_share

    verdict_fallback_calls = monthly_checks * costs.verdict_fallback_rate
    image_fallback_calls = image_checks * costs.image_fallback_rate
    video_fallback_calls = video_checks * costs.video_fallback_rate

    spend = (
        verdict_fallback_calls * costs.verdict_fallback_cost
        + image_fallback_calls * costs.image_fallback_cost
        + video_fallback_calls * costs.video_fallback_cost
    )

    return {
        "checks_per_day": round(checks_per_day, 2),
        "monthly_checks": round(monthly_checks, 2),
        "monthly_openai_spend_usd": round(spend, 2),
        "budget_usd": costs.openai_budget_usd,
        "within_budget": spend <= costs.openai_budget_usd,
    }


if __name__ == "__main__":
    result = simulate(TrafficProfile(), CostProfile())
    print("Mixed traffic simulation")
    for k, v in result.items():
        print(f"{k}: {v}")
