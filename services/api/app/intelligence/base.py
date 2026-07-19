"""Protocols consumed by orchestration without coupling it to model or database SDKs."""

from typing import Protocol
from uuid import UUID

from services.api.app.contracts import (
    FeeCategory,
    JobSpecV1,
    QuoteV1,
    QuoteVerificationResult,
    RecommendationV1,
    TranscriptQuoteFacts,
    VerifiedCompetingQuote,
)


class QuoteCatalog(Protocol):
    def list_quotes(self, job_id: UUID) -> list[QuoteV1]: ...


class IntelligenceProvider(Protocol):
    def verify_quote(
        self,
        provisional_quote: QuoteV1,
        transcript_facts: TranscriptQuoteFacts,
        required_fee_categories: set[FeeCategory] | None = None,
    ) -> QuoteVerificationResult: ...

    def get_verified_competing_quote(
        self,
        job_id: UUID,
        excluded_vendor_id: UUID,
    ) -> VerifiedCompetingQuote | None: ...

    def recommend(self, job_spec: JobSpecV1, quotes: list[QuoteV1]) -> RecommendationV1: ...
