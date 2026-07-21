"""Build bounded, research-aware agendas without treating website text as evidence."""

from __future__ import annotations

import re
from uuid import NAMESPACE_URL, uuid5

from services.api.app.contracts import (
    FeeCategory,
    JobSpecV1,
    VendorCallPlanQuestionV1,
    VendorCallPlanV1,
    VendorCallPlanWebsiteClaimV1,
    VendorResearchDossierV1,
    WebsiteClaimKind,
)
from services.api.app.core.errors import DomainConflict
from services.api.app.orchestration.models import job_spec_sha256

MAX_CALL_PLAN_QUESTIONS = 20
_PHONE_LIKE = re.compile(r"\+?1?[\s.(-]*[2-9]\d{2}[\s.)-]*\d{3}[\s.-]*\d{4}")
_SERVICE_TOPICS = {
    WebsiteClaimKind.PACKING.value,
    WebsiteClaimKind.DISASSEMBLY.value,
    WebsiteClaimKind.STORAGE.value,
    WebsiteClaimKind.INSURANCE.value,
    WebsiteClaimKind.SERVICE.value,
    WebsiteClaimKind.AVAILABILITY.value,
}


def build_vendor_call_plan(
    job_spec: JobSpecV1,
    dossier: VendorResearchDossierV1,
) -> VendorCallPlanV1:
    """Prioritize fee gaps, ambiguity, and relevant services in at most 20 questions."""

    if not job_spec.confirmed or job_spec.locked_version != job_spec.version:
        raise DomainConflict("Vendor call plans require a confirmed, locked JobSpec")
    if dossier.status == "pending":
        raise DomainConflict("Vendor website research must finish before call planning")

    selected: list[VendorCallPlanQuestionV1] = []
    selected_ids: set = set()

    def add(question) -> None:
        if (
            len(selected) >= MAX_CALL_PLAN_QUESTIONS
            or question.question_id in selected_ids
            or _PHONE_LIKE.search(question.question)
        ):
            return
        selected_ids.add(question.question_id)
        selected.append(
            VendorCallPlanQuestionV1(
                question_id=question.question_id,
                category=question.category.value,
                question=question.question,
                reason=question.reason,
                claim_ids=question.claim_ids,
            )
        )

    # First ask each fee category once. A published value is confirmed with its conditions;
    # absent values are requested directly, so the agent never asks the same price twice.
    for category in FeeCategory:
        match = next(
            (
                question
                for question in dossier.verification_questions
                if question.category.value == category.value
            ),
            None,
        )
        if match is not None:
            add(match)

    for question in dossier.verification_questions:
        if question.reason == "ambiguous_claim":
            add(question)
            if sum(item.reason == "ambiguous_claim" for item in selected) == 3:
                break

    service_count = 0
    for question in dossier.verification_questions:
        if question.reason != "published_claim" or question.category.value not in _SERVICE_TOPICS:
            continue
        before = len(selected)
        add(question)
        if len(selected) > before:
            service_count += 1
        if service_count == 2:
            break

    if not selected:
        text = (
            "Please provide one complete itemized all-in quote for the locked move, "
            "including every mandatory fee, availability, binding status, and deposit term."
        )
        selected.append(
            VendorCallPlanQuestionV1(
                question_id=uuid5(
                    NAMESPACE_URL,
                    f"veramove-call-plan:{dossier.vendor.vendor_id}:{text}",
                ),
                category=FeeCategory.BASE_SERVICE.value,
                question=text,
                reason="missing_information",
            )
        )

    relevant_claims = [
        claim
        for claim in dossier.claims
        if not _PHONE_LIKE.search(claim.summary)
    ]
    relevant_claims.sort(
        key=lambda claim: (
            claim.advertised_amount is None,
            claim.kind.value not in _SERVICE_TOPICS,
            str(claim.claim_id),
        )
    )
    website_claims = [
        VendorCallPlanWebsiteClaimV1(
            claim_id=claim.claim_id,
            kind=claim.kind.value,
            summary=claim.summary[:300],
            source_url=claim.source_url,
        )
        for claim in relevant_claims[:5]
    ]
    source_urls = list(
        dict.fromkeys(str(claim.source_url) for claim in website_claims)
    )[:5]

    return VendorCallPlanV1(
        vendor_id=dossier.vendor.vendor_id,
        job_spec_version=job_spec.version,
        job_spec_sha256=job_spec_sha256(job_spec),
        website_claims=website_claims,
        source_urls=source_urls,
        questions=selected,
    )


__all__ = ["build_vendor_call_plan"]
