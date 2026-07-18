"""Default intelligence provider and a mock-friendly quote catalog."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from services.api.app.contracts import (
    FeeCategory,
    JobSpecV1,
    QuoteV1,
    QuoteVerificationResult,
    RecommendationV1,
    TranscriptQuoteFacts,
    VerificationStatus,
    VerifiedCompetingQuote,
)
from services.api.app.intelligence.base import QuoteCatalog
from services.api.app.intelligence.quotes import QuoteVerifier
from services.api.app.intelligence.ranking import DeterministicRecommendationEngine


class InMemoryQuoteCatalog:
    def __init__(self, quotes: list[QuoteV1] | None = None) -> None:
        self._quotes: dict[UUID, list[QuoteV1]] = defaultdict(list)
        for quote in quotes or []:
            self.add(quote)

    def add(self, quote: QuoteV1) -> None:
        self._quotes[quote.job_id].append(quote.model_copy(deep=True))

    def list_quotes(self, job_id: UUID) -> list[QuoteV1]:
        return [quote.model_copy(deep=True) for quote in self._quotes.get(job_id, [])]


class DefaultIntelligenceProvider:
    def __init__(
        self,
        quote_catalog: QuoteCatalog,
        verifier: QuoteVerifier | None = None,
        recommendation_engine: DeterministicRecommendationEngine | None = None,
    ) -> None:
        self._quote_catalog = quote_catalog
        self._verifier = verifier or QuoteVerifier()
        self._recommendation_engine = recommendation_engine or DeterministicRecommendationEngine()

    def verify_quote(
        self,
        provisional_quote: QuoteV1,
        transcript_facts: TranscriptQuoteFacts,
        required_fee_categories: set[FeeCategory] | None = None,
    ) -> QuoteVerificationResult:
        return self._verifier.verify(
            provisional_quote,
            transcript_facts,
            required_fee_categories,
        )

    def get_verified_competing_quote(
        self,
        job_id: UUID,
        excluded_vendor_id: UUID,
    ) -> VerifiedCompetingQuote | None:
        safe: list[QuoteV1] = []
        for quote in self._quote_catalog.list_quotes(job_id):
            total = quote.comparable_total
            if (
                quote.job_id == job_id
                and quote.vendor.vendor_id != excluded_vendor_id
                and quote.verification_status is VerificationStatus.VERIFIED
                and quote.job_spec_version == "1.0"
                and total is not None
                and quote.transcript_evidence
                and not quote.manually_fabricated
            ):
                safe.append(quote)
        if not safe:
            return None
        selected = min(safe, key=lambda quote: quote.comparable_total)
        return VerifiedCompetingQuote(
            quote=selected,
            leverage_total=selected.comparable_total,
            evidence_ids=[evidence.evidence_id for evidence in selected.transcript_evidence],
        )

    def recommend(self, job_spec: JobSpecV1, quotes: list[QuoteV1]) -> RecommendationV1:
        return self._recommendation_engine.recommend(job_spec, quotes)
