"""Deterministic intelligence adapter for credential-free mock workflows."""

from uuid import uuid4

from services.api.app.contracts import IntakeSource, JobSpecV1, QuoteV1
from services.api.app.core.errors import DomainConflict
from services.api.app.integrations.openai.base import NegotiationGateway
from services.api.app.orchestration.fixtures import DemoFixtures


class MockIntelligenceProvider:
    """Use synthetic intake and delegate negotiation to the existing gateway."""

    def __init__(
        self,
        fixtures: DemoFixtures,
        negotiation_gateway: NegotiationGateway,
    ) -> None:
        self._fixtures = fixtures
        self._negotiation_gateway = negotiation_gateway

    def extract_document(self, document_text: str) -> JobSpecV1:
        if not document_text.strip():
            raise DomainConflict("Document text is required")
        job_spec = self._fixtures.load_job()
        return job_spec.model_copy(
            update={
                "job_id": uuid4(),
                "intake_source": IntakeSource.DOCUMENT,
                "confirmed": False,
                "confirmed_at": None,
                "locked_version": None,
            },
            deep=True,
        )

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
