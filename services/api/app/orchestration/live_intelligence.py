"""OpenAI-backed document intake with deterministic negotiation safeguards."""

from pydantic import ValidationError

from services.api.app.contracts import JobSpecV1, QuoteV1
from services.api.app.core.errors import DomainConflict, ProviderRequestError
from services.api.app.integrations.openai.base import (
    DocumentIntakeGateway,
    NegotiationGateway,
)


class LiveIntelligenceProvider:
    """Use live extraction while preserving verified deterministic leverage."""

    def __init__(
        self,
        document_gateway: DocumentIntakeGateway,
        negotiation_gateway: NegotiationGateway,
    ) -> None:
        self._document_gateway = document_gateway
        self._negotiation_gateway = negotiation_gateway

    def extract_document(self, document_text: str) -> JobSpecV1:
        if not document_text.strip():
            raise DomainConflict("Document text is required")
        try:
            result = self._document_gateway.parse_document(
                document_text.encode("utf-8"),
                "text/plain",
                "document-intake.txt",
            )
        except ProviderRequestError:
            raise
        except (ValidationError, ValueError) as exc:
            raise ProviderRequestError("OpenAI returned invalid document extraction") from exc
        return result.job_spec

    def negotiate(
        self,
        job_spec: JobSpecV1,
        quotes: list[QuoteV1],
        verified_competitor: QuoteV1,
    ) -> QuoteV1:
        return self._negotiation_gateway.negotiate(
            job_spec,
            quotes,
            verified_competitor,
        )


__all__ = ["LiveIntelligenceProvider"]
