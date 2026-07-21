"""Bounded research-aware call-plan tests."""

from datetime import UTC, datetime
from decimal import Decimal

from services.api.app.contracts import (
    FeeCategory,
    VendorResearchDossierV1,
    WebsiteClaimKind,
    WebsiteResearchClaimV1,
)
from services.api.app.orchestration.vendor_call_plans import (
    build_vendor_call_plan,
)
from services.api.app.orchestration.vendor_research_questions import (
    build_verification_plan,
)

NOW = datetime(2026, 7, 21, 19, 0, tzinfo=UTC)


def _locked(job_spec):
    return job_spec.model_copy(
        update={
            "confirmed": True,
            "confirmed_at": NOW,
            "locked_version": job_spec.version,
        },
        deep=True,
    )


def test_plan_confirms_published_price_once_and_asks_missing_fees(
    job_spec,
    fixtures,
):
    locked = _locked(job_spec)
    vendor = fixtures.load_vendors()[0]
    claim = WebsiteResearchClaimV1(
        kind=WebsiteClaimKind.HOURLY_RATE,
        summary="Moving services start at $149 per hour for two movers.",
        advertised_amount=Decimal("149"),
        currency="USD",
        unit="hour",
        qualifiers=["starting at"],
        source_url="https://mover.example/pricing",
        source_excerpt="Moving services start at $149 per hour for two movers.",
        retrieved_at=NOW,
    )
    required = {
        FeeCategory.BASE_SERVICE,
        FeeCategory.TRAVEL,
        FeeCategory.FUEL,
        FeeCategory.STAIRS,
        FeeCategory.LONG_CARRY,
        FeeCategory.PACKING,
    }
    questions, missing = build_verification_plan(locked, [claim], required)
    dossier = VendorResearchDossierV1(
        vendor=vendor,
        status="complete",
        claims=[claim],
        missing_fee_categories=missing,
        verification_questions=questions,
        researched_at=NOW,
    )

    plan = build_vendor_call_plan(locked, dossier)

    assert sum("website lists" in item.question.lower() for item in plan.questions) == 1
    assert FeeCategory.TRAVEL.value in {item.category for item in plan.questions}
    assert FeeCategory.FUEL.value in {item.category for item in plan.questions}
    assert len(plan.questions) <= 20
    assert plan.website_claims[0].classification == "unverified_website_claim"


def test_plan_contains_no_phone_contact_or_raw_page(job_spec, fixtures):
    locked = _locked(job_spec)
    vendor = fixtures.load_vendors()[0]
    questions, missing = build_verification_plan(
        locked,
        [],
        {FeeCategory.BASE_SERVICE, FeeCategory.TRAVEL},
    )
    dossier = VendorResearchDossierV1(
        vendor=vendor,
        status="complete",
        missing_fee_categories=missing,
        verification_questions=questions,
        researched_at=NOW,
    )

    payload = build_vendor_call_plan(locked, dossier).model_dump_json()

    assert "+1" not in payload
    assert "normalized_number" not in payload
    assert "raw_content" not in payload
    assert "source_excerpt" not in payload


def test_plan_falls_back_to_one_complete_quote_request(job_spec, fixtures):
    locked = _locked(job_spec)
    dossier = VendorResearchDossierV1(
        vendor=fixtures.load_vendors()[0],
        status="failed",
        researched_at=NOW,
        safe_failure_reason="Synthetic website unavailable.",
    )

    plan = build_vendor_call_plan(locked, dossier)

    assert len(plan.questions) == 1
    assert "complete itemized all-in quote" in plan.questions[0].question
