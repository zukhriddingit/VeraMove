"""Provider-neutral protocols consumed by VeraMove orchestration."""

from typing import Literal, Protocol
from uuid import UUID

from services.api.app.contracts import (
    FeeCategory,
    JobSpecV1,
    QuoteV1,
    QuoteVerificationResult,
    TranscriptQuoteFacts,
    Vendor,
)
from services.api.app.orchestration.models import VoiceCallResult


class VoiceProvider(Protocol):
    """Initiate one provider-neutral quote or negotiation call."""

    initial_call_limit: int

    def initiate_quote_call(
        self,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
        destination_slot: Literal[0, 1, 2],
    ) -> VoiceCallResult: ...

    def initiate_negotiation_call(
        self,
        job_spec: JobSpecV1,
        target_vendor: Vendor,
        verified_competitor: QuoteV1,
        planned_quote: QuoteV1,
        call_id: UUID,
        destination_slot: Literal[0, 1, 2],
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


class QuoteVerificationGateway(Protocol):
    """Verify provisional values against bounded timestamped call evidence."""

    def verify(
        self,
        provisional_quote: QuoteV1,
        transcript_facts: TranscriptQuoteFacts,
        required_fee_categories: set[FeeCategory] | None = None,
    ) -> QuoteVerificationResult: ...
