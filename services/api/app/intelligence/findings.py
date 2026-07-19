"""Machine-readable hidden-fee findings and deterministic red flags."""

from __future__ import annotations

from decimal import Decimal
from statistics import median
from uuid import UUID

from services.api.app.contracts import (
    AmountStatus,
    AvailabilityStatus,
    BindingType,
    FeeCategory,
    FindingSeverity,
    IntelligenceFinding,
    QuoteV1,
)


class HiddenFeeDetector:
    def __init__(self, large_deposit_percent: Decimal = Decimal("25")) -> None:
        self._large_deposit_percent = large_deposit_percent

    def analyze(
        self,
        quote: QuoteV1,
        required_fee_categories: set[FeeCategory] | None = None,
    ) -> list[IntelligenceFinding]:
        findings: list[IntelligenceFinding] = []
        evidence_ids = [item.evidence_id for item in quote.transcript_evidence]
        for fee in quote.fee_line_items:
            if not fee.disclosed_upfront:
                findings.append(
                    self._finding(
                        quote,
                        "hidden_fee_revealed_after_probe",
                        FindingSeverity.WARNING,
                        f"{fee.category.value} was disclosed only after direct questioning.",
                        fee.category,
                        fee.evidence_ids or evidence_ids,
                    )
                )
            if fee.amount_status is AmountStatus.UNKNOWN:
                findings.append(
                    self._finding(
                        quote,
                        "unknown_fee_amount",
                        FindingSeverity.WARNING,
                        f"{fee.category.value} was discussed but its amount remains unknown.",
                        fee.category,
                        fee.evidence_ids or evidence_ids,
                    )
                )

        known_total = self._known_itemized_total(quote)
        if (
            quote.headline_total is not None
            and known_total is not None
            and quote.headline_total < known_total
        ):
            findings.append(
                self._finding(
                    quote,
                    "mandatory_fees_omitted_from_headline",
                    FindingSeverity.CRITICAL,
                    "The headline total is lower than the known itemized total.",
                    evidence_ids=evidence_ids,
                )
            )
        if (
            quote.negotiated_total is not None
            and known_total is not None
            and quote.negotiated_total != known_total
        ):
            findings.append(
                self._finding(
                    quote,
                    "spoken_itemized_total_conflict",
                    FindingSeverity.CRITICAL,
                    "The spoken total conflicts with the sum of known line items.",
                    evidence_ids=evidence_ids,
                )
            )
        if quote.binding_type is BindingType.NON_BINDING:
            findings.append(
                self._finding(
                    quote,
                    "non_binding_estimate",
                    FindingSeverity.WARNING,
                    "The vendor described the quote as non-binding.",
                    evidence_ids=evidence_ids,
                )
            )
        if quote.availability_status is AvailabilityStatus.UNAVAILABLE:
            findings.append(
                self._finding(
                    quote,
                    "move_date_unavailable",
                    FindingSeverity.CRITICAL,
                    "The vendor is unavailable on the requested move date.",
                    evidence_ids=evidence_ids,
                )
            )

        addressed = {item.category for item in quote.fee_line_items}
        for category in sorted(required_fee_categories or set(), key=lambda item: item.value):
            if category not in addressed:
                findings.append(
                    self._finding(
                        quote,
                        "missing_fee_category",
                        FindingSeverity.WARNING,
                        f"{category.value} was not addressed and must not be assumed to be zero.",
                        category,
                    )
                )

        if quote.deposit is not None:
            total = quote.comparable_total
            if total is None:
                total = quote.negotiated_total
            if total is None:
                total = quote.original_total
            if (
                total is not None
                and total > 0
                and quote.deposit * Decimal("100") / total
                > self._large_deposit_percent
            ):
                findings.append(
                    self._finding(
                        quote,
                        "unusually_large_deposit",
                        FindingSeverity.WARNING,
                        f"The deposit exceeds {self._large_deposit_percent}% of the quote total.",
                        FeeCategory.DEPOSIT,
                        evidence_ids,
                    )
                )

        for fee in quote.fee_line_items:
            if (
                fee.category is FeeCategory.HOURLY_MINIMUM
                and fee.minimum_units is None
                and fee.amount_status is not AmountStatus.NOT_APPLICABLE
            ):
                findings.append(
                    self._finding(
                        quote,
                        "unclear_minimum_hours",
                        FindingSeverity.WARNING,
                        "An hourly price was discussed without a clear minimum-hour rule.",
                        FeeCategory.HOURLY_MINIMUM,
                        fee.evidence_ids,
                    )
                )
        return findings

    @staticmethod
    def _known_itemized_total(quote: QuoteV1) -> Decimal | None:
        amounts: list[Decimal] = []
        for fee in quote.fee_line_items:
            if fee.amount_status is AmountStatus.NOT_APPLICABLE:
                continue
            if fee.amount_status is AmountStatus.UNKNOWN:
                return None
            if fee.amount is not None:
                amounts.append(fee.amount)
                continue
            if fee.unit_rate is None:
                return None
            units = max(fee.units or Decimal("0"), fee.minimum_units or Decimal("0"))
            amounts.append(fee.unit_rate * units)
        return sum(amounts, Decimal("0"))

    @staticmethod
    def _finding(
        quote: QuoteV1,
        code: str,
        severity: FindingSeverity,
        description: str,
        fee_category: FeeCategory | None = None,
        evidence_ids: list[UUID] | None = None,
    ) -> IntelligenceFinding:
        return IntelligenceFinding(
            code=code,
            severity=severity,
            description=description,
            vendor_id=quote.vendor.vendor_id,
            quote_id=quote.quote_id,
            fee_category=fee_category,
            evidence_ids=evidence_ids or [],
        )


class DeterministicRedFlagDetector:
    def __init__(self, below_median_percent: Decimal = Decimal("30")) -> None:
        self._below_median_percent = below_median_percent

    def analyze(self, quotes: list[QuoteV1]) -> dict[UUID, list[IntelligenceFinding]]:
        results = {quote.quote_id: self._quote_flags(quote) for quote in quotes}
        comparable = [
            quote.comparable_total for quote in quotes if quote.comparable_total is not None
        ]
        if len(comparable) < 2:
            return results
        comparison_median = Decimal(str(median(comparable)))
        cutoff = comparison_median * (Decimal("1") - self._below_median_percent / Decimal("100"))
        for quote in quotes:
            total = quote.comparable_total
            if total is not None and total <= cutoff:
                results[quote.quote_id].append(
                    IntelligenceFinding(
                        code="thirty_percent_below_median",
                        severity=FindingSeverity.CRITICAL,
                        description=(
                            f"The comparable total is at least {self._below_median_percent}% "
                            "below the median and requires review."
                        ),
                        vendor_id=quote.vendor.vendor_id,
                        quote_id=quote.quote_id,
                        evidence_ids=[
                            evidence.evidence_id for evidence in quote.transcript_evidence
                        ],
                    )
                )
        return results

    @staticmethod
    def _quote_flags(quote: QuoteV1) -> list[IntelligenceFinding]:
        flags: list[IntelligenceFinding] = []
        evidence_ids = [item.evidence_id for item in quote.transcript_evidence]

        def add(code: str, description: str, severity: FindingSeverity) -> None:
            flags.append(
                IntelligenceFinding(
                    code=code,
                    severity=severity,
                    description=description,
                    vendor_id=quote.vendor.vendor_id,
                    quote_id=quote.quote_id,
                    evidence_ids=evidence_ids,
                )
            )

        if quote.comparable_total is None:
            add(
                "lacks_all_in_total",
                "The quote lacks a reliable all-in total.",
                FindingSeverity.CRITICAL,
            )
        if quote.binding_type is BindingType.NON_BINDING:
            add("non_binding_quote", "The quote is non-binding.", FindingSeverity.WARNING)
        if quote.availability_status is AvailabilityStatus.UNAVAILABLE:
            add(
                "vendor_unavailable",
                "The vendor is unavailable on the requested move date.",
                FindingSeverity.CRITICAL,
            )
        if not quote.transcript_evidence:
            add(
                "material_claim_lacks_evidence",
                "Material quote claims lack transcript evidence.",
                FindingSeverity.CRITICAL,
            )
        for finding in quote.findings:
            if finding.code in {
                "missing_fee_category",
                "spoken_itemized_total_conflict",
                "mandatory_fees_omitted_from_headline",
            }:
                flags.append(finding)
        return flags
