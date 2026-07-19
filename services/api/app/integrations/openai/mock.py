"""Deterministic OpenAI-boundary fixtures with no model API calls."""

from services.api.app.contracts import DocumentParseResult, JobSpecV1, QuoteV1
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
        del quotes
        quote = self._fixtures.load_negotiated_quote()
        verified = dict(quote.verified_data)
        verified["competing_quote_id"] = str(verified_competitor.quote_id)
        return quote.model_copy(
            update={"job_id": job_spec.job_id, "verified_data": verified},
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
