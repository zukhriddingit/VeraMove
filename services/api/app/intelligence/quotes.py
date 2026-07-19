"""Quote normalization and transcript-backed verification."""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

from services.api.app.contracts import (
    AmountStatus,
    AvailabilityStatus,
    BindingType,
    FeeCategory,
    FeeLineItem,
    FindingSeverity,
    IntelligenceFinding,
    QuoteV1,
    QuoteVerificationResult,
    TranscriptEvidence,
    TranscriptQuoteFacts,
    VerificationStatus,
)
from services.api.app.intelligence.findings import HiddenFeeDetector

MAX_CLAIM_EVIDENCE_SECONDS = Decimal("30.00")


class QuoteNormalizer:
    def calculate_line_item(self, item: FeeLineItem) -> Decimal | None:
        if item.amount_status is AmountStatus.NOT_APPLICABLE:
            return Decimal("0")
        if item.amount_status is AmountStatus.UNKNOWN:
            return None
        if item.amount is not None:
            return item.amount
        if item.unit_rate is None:
            return None
        units = max(item.units or Decimal("0"), item.minimum_units or Decimal("0"))
        return (item.unit_rate * units).quantize(Decimal("0.01"))

    def calculate_all_in_total(self, line_items: list[FeeLineItem]) -> Decimal | None:
        total = Decimal("0")
        for item in line_items:
            amount = self.calculate_line_item(item)
            if amount is None:
                return None
            total += amount
        return total.quantize(Decimal("0.01"))

    def normalize(self, quote: QuoteV1) -> QuoteV1:
        itemized_total = self.calculate_all_in_total(quote.fee_line_items)
        spoken_total = (
            quote.negotiated_total if quote.negotiated_total is not None else quote.original_total
        )
        comparable_total = itemized_total
        if (
            itemized_total is not None
            and spoken_total is not None
            and itemized_total != spoken_total
        ):
            comparable_total = None
        return quote.model_copy(
            update={
                "original_total": (
                    quote.original_total if quote.original_total is not None else itemized_total
                ),
                "negotiated_total": (
                    quote.negotiated_total if quote.negotiated_total is not None else itemized_total
                ),
                "comparable_total": comparable_total,
            }
        )


def is_measurable_quote_improvement(
    initial: QuoteV1,
    negotiated: QuoteV1,
    *,
    allowed_new_concessions: set[str] | None = None,
) -> bool:
    """Accept only a comparable price, deposit, binding, or configured term gain."""

    if (
        initial.job_id != negotiated.job_id
        or initial.vendor.vendor_id != negotiated.vendor.vendor_id
        or initial.job_spec_version != negotiated.job_spec_version
    ):
        return False
    initial_total = (
        initial.comparable_total
        if initial.comparable_total is not None
        else initial.negotiated_total
    )
    negotiated_total = (
        negotiated.comparable_total
        if negotiated.comparable_total is not None
        else negotiated.negotiated_total
    )
    price_improved = (
        initial_total is not None
        and negotiated_total is not None
        and negotiated_total < initial_total
    )
    deposit_improved = (
        initial.deposit is not None
        and negotiated.deposit is not None
        and negotiated.deposit < initial.deposit
    )
    binding_strength = {
        BindingType.UNKNOWN: 0,
        BindingType.NON_BINDING: 1,
        BindingType.BINDING: 2,
    }
    binding_improved = (
        binding_strength[negotiated.binding_type] > binding_strength[initial.binding_type]
    )
    initial_concessions = {_normalized_term(item) for item in initial.concessions}
    allowed = {_normalized_term(item) for item in allowed_new_concessions or set()}
    added = {_normalized_term(item) for item in negotiated.concessions} - initial_concessions
    configured_term_improved = bool(added & allowed)
    return price_improved or deposit_improved or binding_improved or configured_term_improved


class QuoteVerifier:
    def __init__(
        self,
        normalizer: QuoteNormalizer | None = None,
        hidden_fee_detector: HiddenFeeDetector | None = None,
    ) -> None:
        self._normalizer = normalizer or QuoteNormalizer()
        self._hidden_fee_detector = hidden_fee_detector or HiddenFeeDetector()

    def verify(
        self,
        provisional_quote: QuoteV1,
        transcript_facts: TranscriptQuoteFacts,
        required_fee_categories: set[FeeCategory] | None = None,
    ) -> QuoteVerificationResult:
        valid_evidence = [
            item
            for item in transcript_facts.evidence
            if str(item.recording_url) == str(provisional_quote.recording_url)
            and item.end_seconds - item.start_seconds <= MAX_CLAIM_EVIDENCE_SECONDS
        ]
        if len({item.call_id for item in valid_evidence}) > 1:
            valid_evidence = []
        evidence_by_id = {item.evidence_id: item for item in valid_evidence}
        evidence_ids = list(evidence_by_id)
        provisional_by_category: dict[FeeCategory, list[FeeLineItem]] = defaultdict(list)
        transcript_by_category: dict[FeeCategory, list[FeeLineItem]] = defaultdict(list)
        for item in provisional_quote.fee_line_items:
            provisional_by_category[item.category].append(item)
        for item in transcript_facts.fee_line_items:
            transcript_by_category[item.category].append(item)
        contradictions: list[str] = []
        merged: list[FeeLineItem] = []

        for category in dict.fromkeys([*provisional_by_category, *transcript_by_category]):
            provisional_items = provisional_by_category[category]
            supported_items = transcript_by_category[category]
            item_count = max(len(provisional_items), len(supported_items))
            for index in range(item_count):
                provisional = provisional_items[index] if index < len(provisional_items) else None
                supported = supported_items[index] if index < len(supported_items) else None
                if supported is None and provisional is not None:
                    merged.append(
                        provisional.model_copy(
                            update={
                                "amount": None,
                                "amount_status": AmountStatus.UNKNOWN,
                                "unit_rate": None,
                                "units": None,
                                "minimum_units": None,
                                "evidence_ids": [],
                            }
                        )
                    )
                    continue
                if supported is None:
                    continue
                supporting_evidence = [
                    evidence_by_id[evidence_id]
                    for evidence_id in supported.evidence_ids
                    if evidence_id in evidence_by_id
                    and _evidence_supports_fee(
                        evidence_by_id[evidence_id],
                        supported,
                        self._normalizer,
                    )
                ]
                if supported.amount_status is not AmountStatus.UNKNOWN and not supporting_evidence:
                    merged.append(
                        supported.model_copy(
                            update={
                                "amount": None,
                                "amount_status": AmountStatus.UNKNOWN,
                                "unit_rate": None,
                                "units": None,
                                "minimum_units": None,
                                "evidence_ids": [],
                            }
                        )
                    )
                    continue
                if (
                    provisional is not None
                    and provisional.amount is not None
                    and supported.amount is not None
                    and provisional.amount != supported.amount
                ):
                    contradictions.append(category.value)
                merged.append(
                    supported.model_copy(
                        update={"evidence_ids": [item.evidence_id for item in supporting_evidence]}
                    )
                )

        itemized_total = self._normalizer.calculate_all_in_total(merged)
        missing_evidence_claims = [
            f"fee:{item.category.value}"
            for item in merged
            if item.amount_status is AmountStatus.UNKNOWN
        ]
        total_supported = transcript_facts.spoken_total is None or any(
            _evidence_supports_total(item, transcript_facts.spoken_total) for item in valid_evidence
        )
        if not total_supported:
            missing_evidence_claims.append("quote_total")
        binding_supported = transcript_facts.binding_type is BindingType.UNKNOWN or any(
            _evidence_supports_binding(item, transcript_facts.binding_type)
            for item in valid_evidence
        )
        if not binding_supported:
            missing_evidence_claims.append("binding_status")
        availability_supported = (
            transcript_facts.availability_status is AvailabilityStatus.UNKNOWN
            or any(
                _evidence_supports_availability(
                    item,
                    transcript_facts.availability_status,
                )
                for item in valid_evidence
            )
        )
        if not availability_supported:
            missing_evidence_claims.append("availability_status")
        total_conflict = (
            itemized_total is not None
            and transcript_facts.spoken_total is not None
            and itemized_total != transcript_facts.spoken_total
        )
        comparable_total = None if total_conflict else itemized_total
        verification_status = VerificationStatus.PARTIALLY_VERIFIED
        if valid_evidence and comparable_total is not None and not missing_evidence_claims:
            verification_status = VerificationStatus.VERIFIED

        verified = provisional_quote.model_copy(
            update={
                "fee_line_items": merged,
                "original_total": (
                    transcript_facts.spoken_total
                    if transcript_facts.spoken_total is not None
                    else itemized_total
                ),
                "negotiated_total": (
                    transcript_facts.spoken_total
                    if transcript_facts.spoken_total is not None
                    else itemized_total
                ),
                "comparable_total": comparable_total,
                "binding_type": transcript_facts.binding_type,
                "availability": transcript_facts.availability,
                "availability_status": transcript_facts.availability_status,
                "verification_status": verification_status,
                "transcript_evidence": valid_evidence,
                "verified_data": {
                    **provisional_quote.verified_data,
                    "provisional_preserved": True,
                    "contradicted_fee_categories": list(dict.fromkeys(contradictions)),
                    "addressed_fee_categories": [
                        item.value for item in transcript_facts.addressed_fee_categories
                    ],
                    "itemized_total": str(itemized_total) if itemized_total is not None else None,
                    "missing_evidence_claims": list(dict.fromkeys(missing_evidence_claims)),
                },
            }
        )
        findings = self._hidden_fee_detector.analyze(verified, required_fee_categories)
        if contradictions:
            findings.append(
                IntelligenceFinding(
                    code="provisional_transcript_contradiction",
                    severity=FindingSeverity.CRITICAL,
                    description=(
                        "Transcript-backed amounts corrected contradictory provisional fields: "
                        + ", ".join(sorted(set(contradictions)))
                    ),
                    vendor_id=verified.vendor.vendor_id,
                    quote_id=verified.quote_id,
                    evidence_ids=evidence_ids,
                )
            )
        verified = verified.model_copy(update={"findings": findings})

        follow_up_questions = [
            f"Please confirm the amount for {item.category.value}."
            for item in merged
            if item.amount_status is AmountStatus.UNKNOWN
        ]
        missing_categories = sorted(
            (required_fee_categories or set()) - set(transcript_facts.addressed_fee_categories),
            key=lambda item: item.value,
        )
        follow_up_questions.extend(
            f"Does the quote include any {category.value} charge?"
            for category in missing_categories
        )
        return QuoteVerificationResult(
            verified_quote=verified,
            findings=findings,
            follow_up_questions=follow_up_questions,
        )


def _normalized_term(value: str) -> str:
    return " ".join(value.casefold().split())


def _evidence_text(evidence: TranscriptEvidence) -> str:
    value = f"{evidence.claim} {evidence.excerpt}".casefold()
    return " ".join(re.sub(r"[^a-z0-9.]+", " ", value.replace(",", "").replace("$", "")).split())


def _amount_is_present(text: str, amount: Decimal) -> bool:
    exact = format(amount, "f")
    compact = exact.rstrip("0").rstrip(".")
    return any(
        re.search(rf"(?<!\d){re.escape(value)}(?!\d)", text) is not None
        for value in {exact, compact}
    )


def _evidence_supports_fee(
    evidence: TranscriptEvidence,
    item: FeeLineItem,
    normalizer: QuoteNormalizer,
) -> bool:
    text = _evidence_text(evidence)
    category = item.category.value.replace("_", " ")
    aliases = {
        FeeCategory.BASE_SERVICE: ("base service", "base fee"),
        FeeCategory.HOURLY_MINIMUM: ("hourly minimum", "minimum hours"),
        FeeCategory.LONG_CARRY: ("long carry",),
    }.get(item.category, (category,))
    if not any(alias in text for alias in aliases):
        return False
    if item.amount_status is AmountStatus.NOT_APPLICABLE:
        return True
    amount = normalizer.calculate_line_item(item)
    return amount is None or _amount_is_present(text, amount)


def _evidence_supports_total(
    evidence: TranscriptEvidence,
    total: Decimal,
) -> bool:
    text = _evidence_text(evidence)
    has_total_term = any(term in text for term in ("total", "all in", "price", "quote amount"))
    return has_total_term and _amount_is_present(text, total)


def _evidence_supports_binding(
    evidence: TranscriptEvidence,
    binding_type: BindingType,
) -> bool:
    text = _evidence_text(evidence)
    non_binding = "non binding" in text or "not binding" in text
    if binding_type is BindingType.NON_BINDING:
        return non_binding
    if binding_type is BindingType.BINDING:
        return "binding" in text and not non_binding
    return True


def _evidence_supports_availability(
    evidence: TranscriptEvidence,
    availability_status: AvailabilityStatus,
) -> bool:
    text = _evidence_text(evidence)
    unavailable = any(term in text for term in ("unavailable", "not available", "no availability"))
    if availability_status is AvailabilityStatus.UNAVAILABLE:
        return unavailable
    if availability_status is AvailabilityStatus.AVAILABLE:
        return (
            any(term in text for term in ("available", "slot confirmed", "date confirmed"))
            and not unavailable
        )
    return True
