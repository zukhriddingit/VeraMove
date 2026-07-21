"""Pure verification-question planning for unverified website statements."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from services.api.app.contracts import (
    FeeCategory,
    JobSpecV1,
    VendorVerificationQuestionV1,
    WebsiteClaimKind,
    WebsiteResearchClaimV1,
)

MAX_QUESTIONS = 40

_CLAIM_FEE_MAP = {
    WebsiteClaimKind.HOURLY_RATE: FeeCategory.BASE_SERVICE,
    WebsiteClaimKind.MINIMUM_HOURS: FeeCategory.HOURLY_MINIMUM,
    **{
        WebsiteClaimKind(category.value): category
        for category in FeeCategory
        if category.value in WebsiteClaimKind._value2member_map_
    },
}

_FEE_LABELS = {
    FeeCategory.BASE_SERVICE: "base moving-service rate",
    FeeCategory.HOURLY_MINIMUM: "hourly minimum and minimum billable time",
    FeeCategory.TRAVEL: "travel-time or trip charge",
    FeeCategory.FUEL: "fuel surcharge",
    FeeCategory.STAIRS: "stair-carry charge",
    FeeCategory.ELEVATOR: "elevator charge",
    FeeCategory.LONG_CARRY: "long-carry charge",
    FeeCategory.PACKING: "packing-service charge",
    FeeCategory.MATERIALS: "packing-material charge",
    FeeCategory.DISASSEMBLY: "furniture disassembly/reassembly charge",
    FeeCategory.STORAGE: "storage charge",
    FeeCategory.INSURANCE: "valuation or insurance charge",
    FeeCategory.TAX: "tax",
    FeeCategory.DEPOSIT: "deposit",
    FeeCategory.OTHER: "other mandatory charge",
}


def _stable_question_id(
    category: FeeCategory | WebsiteClaimKind,
    reason: str,
    question: str,
) -> UUID:
    return uuid5(NAMESPACE_URL, f"veramove:{category.value}:{reason}:{question}")


def _amount_text(claim: WebsiteResearchClaimV1) -> str:
    if claim.advertised_amount is None:
        return ""
    amount: Decimal = claim.advertised_amount
    normalized = format(amount, "f").rstrip("0").rstrip(".")
    prefix = "$" if claim.currency == "USD" else f"{claim.currency or ''} "
    unit = f" per {claim.unit}" if claim.unit else ""
    return f" ({prefix}{normalized}{unit})"


def _claim_question(claim: WebsiteResearchClaimV1) -> str:
    return (
        f'Your website lists "{claim.summary}"{_amount_text(claim)}. '
        "Does that published term apply to this exact move, and what conditions, minimums, "
        "and additional fees apply?"
    )


def _missing_question(category: FeeCategory, job_spec: JobSpecV1) -> str:
    label = _FEE_LABELS[category]
    if category is FeeCategory.STAIRS:
        return (
            "What stair-carry fees apply for the stated origin and destination "
            f"access ({job_spec.origin.stairs or 0} origin stairs and "
            f"{job_spec.destination.stairs or 0} destination stairs)?"
        )
    if category is FeeCategory.ELEVATOR:
        return (
            "What elevator fees or reservation requirements apply given the "
            f"stated access (origin elevator={bool(job_spec.origin.elevator_access)}, "
            f"destination elevator={bool(job_spec.destination.elevator_access)})?"
        )
    if category is FeeCategory.LONG_CARRY:
        return (
            "What long-carry fees apply for the stated parking distances "
            f"({job_spec.origin.parking_distance_feet or 0} ft at origin and "
            f"{job_spec.destination.parking_distance_feet or 0} ft at destination)?"
        )
    if category is FeeCategory.DISASSEMBLY:
        return (
            "What furniture disassembly or reassembly fees apply to the locked "
            f"move specification (requested={bool(job_spec.services.disassembly)})?"
        )
    if category is FeeCategory.PACKING:
        return (
            "What packing-service fees apply to the locked move specification "
            f"(requested={bool(job_spec.services.packing)})?"
        )
    if category is FeeCategory.STORAGE:
        return (
            "What storage fees, minimums, or access conditions apply to the locked "
            f"move specification (requested={bool(job_spec.services.storage)})?"
        )
    return f"What is the complete {label}, and is it included in the all-in total?"


def _ambiguous_question(
    claim: WebsiteResearchClaimV1,
    claims: list[WebsiteResearchClaimV1],
) -> str | None:
    reasons = list(claim.qualifiers)
    if claim.advertised_amount is not None and claim.unit is None:
        reasons.append("the price has no billing unit")
    if (
        claim.kind is WebsiteClaimKind.HOURLY_RATE
        and not any(item.kind is WebsiteClaimKind.MOVER_COUNT for item in claims)
    ):
        reasons.append("the included mover count is not published")
    if not reasons:
        return None
    return (
        f'Please clarify the limits on the website statement "{claim.summary}": '
        f"{'; '.join(dict.fromkeys(reasons))}. What exact terms apply to this move?"
    )


def build_verification_plan(
    job_spec: JobSpecV1,
    claims: Iterable[WebsiteResearchClaimV1],
    required_fee_categories: set[FeeCategory],
) -> tuple[list[VendorVerificationQuestionV1], list[FeeCategory]]:
    """Cover every required fee while preserving website claims as unverified."""

    claim_list = list(claims)[:20]
    claims_by_fee: dict[FeeCategory, list[WebsiteResearchClaimV1]] = {}
    for claim in claim_list:
        category = _CLAIM_FEE_MAP.get(claim.kind)
        if category is not None:
            claims_by_fee.setdefault(category, []).append(claim)

    required_order = [
        category for category in FeeCategory if category in required_fee_categories
    ]
    missing = [category for category in required_order if category not in claims_by_fee]
    questions: list[VendorVerificationQuestionV1] = []
    seen_text: set[str] = set()
    covered_claim_ids: set[UUID] = set()

    def add(
        category: FeeCategory | WebsiteClaimKind,
        question: str,
        reason: str,
        claim_ids: list[UUID] | None = None,
    ) -> None:
        if len(questions) >= MAX_QUESTIONS or question in seen_text:
            return
        seen_text.add(question)
        questions.append(
            VendorVerificationQuestionV1(
                question_id=_stable_question_id(category, reason, question),
                category=category,
                question=question,
                reason=reason,
                claim_ids=claim_ids or [],
            )
        )

    # First guarantee one question for every mandatory fee category.
    for category in required_order:
        fee_claims = claims_by_fee.get(category, [])
        if fee_claims:
            claim = fee_claims[0]
            covered_claim_ids.add(claim.claim_id)
            add(
                category,
                _claim_question(claim),
                "published_claim",
                [claim.claim_id],
            )
        else:
            add(
                category,
                _missing_question(category, job_spec),
                "missing_information",
            )

    # Then confirm non-mandatory or duplicate published statements.
    for claim in claim_list:
        if claim.claim_id in covered_claim_ids:
            continue
        add(
            claim.kind,
            _claim_question(claim),
            "published_claim",
            [claim.claim_id],
        )

    # Use remaining capacity for explicit ambiguity probes.
    for claim in claim_list:
        question = _ambiguous_question(claim, claim_list)
        if question is None:
            continue
        add(
            claim.kind,
            question,
            "ambiguous_claim",
            [claim.claim_id],
        )

    return questions, missing


__all__ = ["build_verification_plan"]
