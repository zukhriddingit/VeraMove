"""Protocol for a future model-backed negotiation implementation."""

from typing import Protocol

from services.api.app.contracts import JobSpecV1, QuoteV1


class NegotiationGateway(Protocol):
    def negotiate(
        self,
        job_spec: JobSpecV1,
        quotes: list[QuoteV1],
        verified_competitor: QuoteV1,
    ) -> QuoteV1: ...
