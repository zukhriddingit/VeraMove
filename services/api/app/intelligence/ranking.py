"""Evidence-backed deterministic ranking with an optional grounded narrator."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from services.api.app.contracts import (
    AvailabilityStatus,
    BindingType,
    IntelligenceFinding,
    JobSpecV1,
    QuoteV1,
    RecommendationRanking,
    RecommendationV1,
    VerificationStatus,
)
from services.api.app.intelligence.findings import DeterministicRedFlagDetector


class RecommendationNarrator(Protocol):
    def explain(
        self,
        job_spec: JobSpecV1,
        rankings: list[RecommendationRanking],
        findings: list[IntelligenceFinding],
    ) -> str: ...


def is_quote_eligible(
    quote: QuoteV1,
    *,
    job_id: UUID,
    job_spec_version: str,
) -> bool:
    """Return whether a quote may influence a recommendation."""

    recording_url = getattr(quote, "recording_url", None)
    evidence = getattr(quote, "transcript_evidence", [])
    return (
        quote.job_id == job_id
        and quote.job_spec_version == job_spec_version
        and quote.verification_status is VerificationStatus.VERIFIED
        and not quote.manually_fabricated
        and recording_url is not None
        and bool(evidence)
        and len({item.call_id for item in evidence}) == 1
        and all(str(item.recording_url) == str(recording_url) for item in evidence)
    )


def is_quote_eligible_for_leverage(
    quote: QuoteV1,
    *,
    job_id: UUID,
    job_spec_version: str,
) -> bool:
    """Apply ranking safety gates plus the comparable-price leverage requirement."""

    return (
        is_quote_eligible(
            quote,
            job_id=job_id,
            job_spec_version=job_spec_version,
        )
        and quote.comparable_total is not None
    )


class DeterministicRecommendationEngine:
    def __init__(
        self,
        red_flag_detector: DeterministicRedFlagDetector | None = None,
        narrator: RecommendationNarrator | None = None,
    ) -> None:
        self._red_flag_detector = red_flag_detector or DeterministicRedFlagDetector()
        self._narrator = narrator

    def recommend(self, job_spec: JobSpecV1, quotes: list[QuoteV1]) -> RecommendationV1:
        eligible_quotes = [
            quote
            for quote in quotes
            if is_quote_eligible(
                quote,
                job_id=job_spec.job_id,
                job_spec_version=job_spec.version,
            )
        ]
        if not eligible_quotes:
            raise ValueError("at least one eligible verified quote is required")
        flags_by_quote = self._red_flag_detector.analyze(eligible_quotes)
        ordered = sorted(
            eligible_quotes,
            key=lambda quote: self._sort_key(quote, flags_by_quote),
        )
        rankings = [
            self._ranking(index, quote, flags_by_quote[quote.quote_id])
            for index, quote in enumerate(ordered, start=1)
        ]
        findings = [finding for quote in ordered for finding in flags_by_quote[quote.quote_id]]
        evidence = []
        seen_evidence = set()
        for quote in ordered:
            for item in quote.transcript_evidence:
                if item.evidence_id not in seen_evidence:
                    evidence.append(item)
                    seen_evidence.add(item.evidence_id)
        if not evidence:
            raise ValueError("recommendations require transcript evidence")

        comparable = [quote for quote in eligible_quotes if quote.comparable_total is not None]
        cheapest = min(comparable, key=lambda quote: quote.comparable_total) if comparable else None
        summary = self._default_summary(ordered[0], cheapest)
        if self._narrator is not None:
            summary = self._narrator.explain(job_spec, rankings, findings)
        uncertainty = [
            f"{quote.vendor.name} lacks a comparable all-in total."
            for quote in eligible_quotes
            if quote.comparable_total is None
        ]
        uncertainty.extend(
            f"{quote.vendor.name} availability is not confirmed."
            for quote in eligible_quotes
            if quote.availability_status is AvailabilityStatus.UNKNOWN
        )
        hidden_fee_codes = {
            "hidden_fee_revealed_after_probe",
            "mandatory_fees_omitted_from_headline",
            "missing_fee_category",
            "unknown_fee_amount",
        }
        hidden_findings = [
            finding
            for quote in eligible_quotes
            for finding in quote.findings
            if finding.code in hidden_fee_codes
        ]
        return RecommendationV1(
            recommendation_id=uuid4(),
            job_id=job_spec.job_id,
            generated_at=datetime.now(UTC),
            summary=summary,
            winning_vendor_id=ordered[0].vendor.vendor_id,
            cheapest_vendor_id=cheapest.vendor.vendor_id if cheapest is not None else None,
            best_value_vendor_id=ordered[0].vendor.vendor_id,
            rankings=rankings,
            evidence_ids=[item.evidence_id for item in evidence],
            transcript_evidence=evidence,
            assumptions=[
                "Ranking uses deterministic price, completeness, binding, and risk rules."
            ],
            uncertainty=uncertainty,
            hidden_fee_findings=hidden_findings,
        )

    @staticmethod
    def _sort_key(
        quote: QuoteV1,
        flags_by_quote: dict,
    ) -> tuple[int, int, int, int, Decimal, int]:
        total = quote.comparable_total
        return (
            quote.availability_status is AvailabilityStatus.UNAVAILABLE,
            total is None,
            quote.binding_type is not BindingType.BINDING,
            len(flags_by_quote[quote.quote_id]),
            total if total is not None else Decimal("Infinity"),
            -len(quote.concessions),
        )

    @staticmethod
    def _ranking(
        rank: int,
        quote: QuoteV1,
        findings: list[IntelligenceFinding],
    ) -> RecommendationRanking:
        rationale: list[str] = []
        total = quote.comparable_total
        rationale.append(
            f"Comparable total: {total} USD." if total is not None else "All-in total is unknown."
        )
        rationale.append(
            "Binding quote." if quote.binding_type is BindingType.BINDING else "Not binding."
        )
        rationale.append(
            "Available on the move date."
            if quote.availability_status is AvailabilityStatus.AVAILABLE
            else f"Availability: {quote.availability_status.value}."
        )
        if quote.concessions:
            rationale.append(f"{len(quote.concessions)} documented concession(s).")
        evidence_ids = [item.evidence_id for item in quote.transcript_evidence]
        if not evidence_ids:
            raise ValueError(f"quote {quote.quote_id} cannot be ranked without evidence")
        return RecommendationRanking(
            rank=rank,
            vendor=quote.vendor,
            quote_id=quote.quote_id,
            total=total,
            rationale=rationale,
            red_flags=[finding.description for finding in findings],
            evidence_ids=evidence_ids,
        )

    @staticmethod
    def _default_summary(best_value: QuoteV1, cheapest: QuoteV1 | None) -> str:
        if cheapest is None:
            return (
                f"{best_value.vendor.name} is the best supported value, but no quote has enough "
                "verified information for a trustworthy cheapest-vendor comparison."
            )
        if best_value.vendor.vendor_id == cheapest.vendor.vendor_id:
            return (
                f"{best_value.vendor.name} is both the cheapest supported option and the best "
                "value after deterministic completeness, binding, availability, and risk checks."
            )
        return (
            f"{best_value.vendor.name} is the best value after deterministic completeness, "
            f"binding, availability, and risk checks. {cheapest.vendor.name} is cheaper, but "
            "the tradeoffs shown in the evidence prevent treating price alone as the winner."
        )
