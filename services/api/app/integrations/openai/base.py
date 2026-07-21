"""Protocols for model-backed parsing, narration, and negotiation."""

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel

from services.api.app.contracts import (
    DocumentParseResult,
    IntelligenceFinding,
    JobSpecV1,
    QuoteV1,
    RecommendationRanking,
    Vendor,
    WebsiteResearchClaimV1,
)
from services.api.app.integrations.tavily.base import ExtractedWebPage


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


class StructuredTextClient(Protocol):
    def parse_text(
        self,
        *,
        model: str,
        capability: str,
        schema_name: str,
        system_prompt: str,
        user_text: str,
        response_schema: type[BaseModel],
    ) -> dict[str, Any]: ...


class WebsiteClaimExtractor(Protocol):
    def extract(
        self,
        vendor: Vendor,
        page: ExtractedWebPage,
        retrieved_at: datetime,
    ) -> list[WebsiteResearchClaimV1]: ...


class GroundedNarrativeClient(Protocol):
    def explain(
        self,
        *,
        model: str,
        job_spec: JobSpecV1,
        rankings: list[RecommendationRanking],
        findings: list[IntelligenceFinding],
    ) -> str: ...


class OpenAIJsonTransport(Protocol):
    """Minimal injectable boundary for one OpenAI JSON request."""

    def post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...
