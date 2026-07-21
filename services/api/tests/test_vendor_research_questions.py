"""Deterministic call-verification planning for unverified website research."""

from datetime import UTC, datetime
from decimal import Decimal

from services.api.app.contracts import (
    FeeCategory,
    WebsiteClaimKind,
    WebsiteResearchClaimV1,
)
from services.api.app.orchestration.vendor_research_questions import (
    build_verification_plan,
)

NOW = datetime(2026, 7, 21, 19, 0, tzinfo=UTC)


def _claim(
    kind: WebsiteClaimKind,
    summary: str,
    *,
    amount: Decimal | None = None,
    unit: str | None = None,
    qualifiers: list[str] | None = None,
) -> WebsiteResearchClaimV1:
    return WebsiteResearchClaimV1(
        kind=kind,
        summary=summary,
        advertised_amount=amount,
        currency="USD" if amount is not None else None,
        unit=unit,
        qualifiers=qualifiers or [],
        source_url="https://mover.example/pricing",
        source_excerpt=summary,
        retrieved_at=NOW,
    )


def test_planner_verifies_claim_and_every_missing_required_fee(job_spec):
    required = {
        FeeCategory.BASE_SERVICE,
        FeeCategory.HOURLY_MINIMUM,
        FeeCategory.STAIRS,
        FeeCategory.LONG_CARRY,
        FeeCategory.DISASSEMBLY,
    }
    claim = _claim(
        WebsiteClaimKind.HOURLY_RATE,
        "Moving services starting at $149/hour.",
        amount=Decimal("149"),
        unit="hour",
        qualifiers=["starting at"],
    )

    questions, missing = build_verification_plan(job_spec, [claim], required)

    assert FeeCategory.BASE_SERVICE not in missing
    assert missing == [
        FeeCategory.HOURLY_MINIMUM,
        FeeCategory.STAIRS,
        FeeCategory.LONG_CARRY,
        FeeCategory.DISASSEMBLY,
    ]
    assert any(
        "$149" in item.question and item.reason == "published_claim"
        for item in questions
    )
    assert any(
        item.category == FeeCategory.STAIRS
        and "stairs" in item.question.casefold()
        for item in questions
    )
    assert any(
        item.category == FeeCategory.LONG_CARRY
        and "carry" in item.question.casefold()
        for item in questions
    )
    assert any(item.reason == "ambiguous_claim" for item in questions)
    assert len(questions) <= 40


def test_planner_is_stable_deduplicated_and_capped(job_spec):
    required = set(FeeCategory)
    claims = [
        _claim(
            WebsiteClaimKind.SERVICE,
            f"Synthetic service statement {index}.",
        )
        for index in range(20)
    ]

    first, first_missing = build_verification_plan(job_spec, claims, required)
    second, second_missing = build_verification_plan(job_spec, claims, required)

    assert first == second
    assert first_missing == second_missing
    assert len(first) <= 40
    assert len({item.question_id for item in first}) == len(first)
    assert len({item.question for item in first}) == len(first)
    for category in required:
        assert any(item.category == category for item in first)

