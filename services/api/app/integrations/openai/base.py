"""Protocols for model-backed parsing, narration, and negotiation."""

from typing import Any, Protocol

from services.api.app.contracts import (
    DocumentParseResult,
    IntelligenceFinding,
    JobSpecV1,
    QuoteV1,
    RecommendationRanking,
)


class NegotiationGateway(Protocol):
    def negotiate(
        self,
        job_spec: JobSpecV1,
        quotes: list[QuoteV1],
        verified_competitor: QuoteV1,
    ) -> QuoteV1: ...


class DocumentIntakeGateway(Protocol):
    def parse_document(
        self,
        content: bytes,
        mime_type: str,
        source_id: str,
    ) -> DocumentParseResult: ...


class StructuredDocumentClient(Protocol):
    def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        content: bytes,
        mime_type: str,
        source_id: str,
        response_schema: type[DocumentParseResult],
    ) -> DocumentParseResult | dict[str, Any]: ...


class GroundedNarrativeClient(Protocol):
    def explain(
        self,
        *,
        model: str,
        job_spec: JobSpecV1,
        rankings: list[RecommendationRanking],
        findings: list[IntelligenceFinding],
    ) -> str: ...
