"""Quote normalization and transcript-backed verification."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from services.api.app.contracts import (
    AmountStatus,
    FeeCategory,
    FeeLineItem,
    FindingSeverity,
    IntelligenceFinding,
    QuoteV1,
    QuoteVerificationResult,
    TranscriptQuoteFacts,
    VerificationStatus,
)
from services.api.app.intelligence.findings import HiddenFeeDetector


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
            quote.negotiated_total
            if quote.negotiated_total is not None
            else quote.original_total
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
                    quote.original_total
                    if quote.original_total is not None
                    else itemized_total
                ),
                "negotiated_total": (
                    quote.negotiated_total
                    if quote.negotiated_total is not None
                    else itemized_total
                ),
                "comparable_total": comparable_total,
            }
        )


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
        evidence_ids = [item.evidence_id for item in transcript_facts.evidence]
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
                provisional = (
                    provisional_items[index] if index < len(provisional_items) else None
                )
                supported = (
                    supported_items[index] if index < len(supported_items) else None
                )
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
                if (
                    provisional is not None
                    and provisional.amount is not None
                    and supported.amount is not None
                    and provisional.amount != supported.amount
                ):
                    contradictions.append(category.value)
                merged.append(
                    supported.model_copy(
                        update={"evidence_ids": supported.evidence_ids or evidence_ids}
                    )
                )

        itemized_total = self._normalizer.calculate_all_in_total(merged)
        total_conflict = (
            itemized_total is not None
            and transcript_facts.spoken_total is not None
            and itemized_total != transcript_facts.spoken_total
        )
        comparable_total = None if total_conflict else itemized_total
        verification_status = VerificationStatus.PARTIALLY_VERIFIED
        if transcript_facts.evidence and comparable_total is not None:
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
                "transcript_evidence": transcript_facts.evidence,
                "verified_data": {
                    **provisional_quote.verified_data,
                    "provisional_preserved": True,
                    "contradicted_fee_categories": list(dict.fromkeys(contradictions)),
                    "addressed_fee_categories": [
                        item.value for item in transcript_facts.addressed_fee_categories
                    ],
                    "itemized_total": str(itemized_total) if itemized_total is not None else None,
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
