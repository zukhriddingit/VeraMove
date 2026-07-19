"""Deterministic OpenAI-boundary fixtures with no model API calls."""

from decimal import Decimal

from services.api.app.contracts import (
    DataClassification,
    DocumentParseResult,
    JobSpecV1,
    QuoteV1,
)
from services.api.app.orchestration.fixtures import DemoFixtures


class MockNegotiationGateway:
    def __init__(self, fixtures: DemoFixtures) -> None:
        self._fixtures = fixtures

    def negotiate(
        self,
        job_spec: JobSpecV1,
        quotes: list[QuoteV1],
        verified_competitor: QuoteV1,
    ) -> QuoteV1:
        quote = self._fixtures.load_negotiated_quote()
        target = max(
            quotes,
            key=lambda item: (
                item.comparable_total
                if item.comparable_total is not None
                else Decimal("-1")
            ),
        )
        if target.vendor.data_classification is DataClassification.ROLE_PLAY:
            return self._role_play_plan(
                quote,
                job_spec,
                target,
                verified_competitor,
            )
        verified = dict(quote.verified_data)
        verified["competing_quote_id"] = str(verified_competitor.quote_id)
        return quote.model_copy(
            update={"job_id": job_spec.job_id, "verified_data": verified},
        )

    @staticmethod
    def _role_play_plan(
        template: QuoteV1,
        job_spec: JobSpecV1,
        target: QuoteV1,
        verified_competitor: QuoteV1,
    ) -> QuoteV1:
        target_total = (
            target.comparable_total
            or target.negotiated_total
            or target.headline_total
        )
        if target_total is None:
            raise ValueError("role-play negotiation requires a target total")
        reduction = min(Decimal("100.00"), target_total)
        improved_total = target_total - reduction
        fee_items = [item.model_copy(deep=True) for item in target.fee_line_items]
        for index, item in enumerate(fee_items):
            if item.amount is not None and item.amount >= reduction:
                fee_items[index] = item.model_copy(
                    update={"amount": item.amount - reduction},
                    deep=True,
                )
                break
        deposit = target.deposit
        improved_deposit = (
            max(Decimal("0.00"), deposit - Decimal("40.00"))
            if deposit is not None
            else None
        )
        verified = dict(target.verified_data)
        verified.update(
            {
                "competing_quote_id": str(verified_competitor.quote_id),
                "price_reduction": str(reduction),
            }
        )
        return template.model_copy(
            update={
                "job_id": job_spec.job_id,
                "vendor": target.vendor.model_copy(deep=True),
                "fee_line_items": fee_items,
                "headline_total": improved_total,
                "original_total": target_total,
                "negotiated_total": improved_total,
                "comparable_total": improved_total,
                "deposit": improved_deposit,
                "binding_type": target.binding_type,
                "availability": target.availability,
                "availability_status": target.availability_status,
                "concessions": [
                    f"Synthetic price reduced by {reduction} USD after verified leverage",
                    "Synthetic deposit reduced by 40 USD",
                ],
                "red_flags": [],
                "findings": [],
                "provisional_data": dict(target.provisional_data),
                "verified_data": verified,
                "transcript_evidence": [
                    item.model_copy(deep=True)
                    for item in target.transcript_evidence
                ],
                "recording_url": target.recording_url,
                "data_classification": DataClassification.ROLE_PLAY,
            },
            deep=True,
        )


class MockDocumentIntakeGateway:
    def __init__(self, result: DocumentParseResult) -> None:
        self._result = result

    def parse_document(
        self,
        content: bytes,
        mime_type: str,
        source_id: str,
    ) -> DocumentParseResult:
        del content, mime_type, source_id
        return self._result.model_copy(deep=True)
