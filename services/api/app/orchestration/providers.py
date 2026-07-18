"""Provider-neutral protocols consumed by VeraMove orchestration."""

from typing import Protocol
from uuid import UUID

from services.api.app.contracts import JobSpecV1, QuoteV1, Vendor
from services.api.app.orchestration.models import VoiceCallResult


class VoiceProvider(Protocol):
    """Initiate one provider-neutral quote or negotiation call."""

    initial_call_limit: int

    def initiate_quote_call(
        self,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
    ) -> VoiceCallResult: ...

    def initiate_negotiation_call(
        self,
        job_spec: JobSpecV1,
        target_vendor: Vendor,
        verified_competitor: QuoteV1,
        planned_quote: QuoteV1,
        call_id: UUID,
    ) -> VoiceCallResult: ...


class IntelligenceProvider(Protocol):
    """Convert intake and plan negotiation without naming a model vendor."""

    def extract_document(self, document_text: str) -> JobSpecV1: ...

    def negotiate(
        self,
        job_spec: JobSpecV1,
        quotes: list[QuoteV1],
        verified_competitor: QuoteV1,
    ) -> QuoteV1: ...
