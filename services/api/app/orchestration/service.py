"""Minimal stateful mock implementation of the VeraMove MVP loop."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from services.api.app.contracts import (
    ElevenLabsWebhookEvent,
    JobRecord,
    JobSpecV1,
    JobState,
    QuoteV1,
    RecommendationV1,
    Vendor,
    VerificationStatus,
    WebhookAck,
)
from services.api.app.core.errors import DomainConflict, ResourceNotFound
from services.api.app.core.state_machine import validate_transition
from services.api.app.integrations.elevenlabs.base import VoiceVendorGateway
from services.api.app.integrations.openai.base import NegotiationGateway
from services.api.app.integrations.tavily.base import VendorDiscoveryGateway
from services.api.app.orchestration.fixtures import DemoFixtures
from services.api.app.repositories.base import JobRepository


class VeraMoveService:
    def __init__(
        self,
        repository: JobRepository,
        voice_gateway: VoiceVendorGateway,
        negotiation_gateway: NegotiationGateway,
        discovery_gateway: VendorDiscoveryGateway,
        fixtures: DemoFixtures,
    ) -> None:
        self._repository = repository
        self._voice_gateway = voice_gateway
        self._negotiation_gateway = negotiation_gateway
        self._discovery_gateway = discovery_gateway
        self._fixtures = fixtures

    def create_job(self, job_spec: JobSpecV1) -> JobRecord:
        if job_spec.confirmed:
            raise DomainConflict("New jobs must be unconfirmed")
        now = datetime.now(UTC)
        return self._repository.create(
            JobRecord(
                job_spec=job_spec,
                state=JobState.INTAKE_COMPLETE,
                created_at=now,
                updated_at=now,
            )
        )

    def get_job(self, job_id: UUID) -> JobRecord:
        record = self._repository.get(job_id)
        if record is None:
            raise ResourceNotFound(f"Job {job_id} was not found")
        return record

    def confirm_job(self, job_id: UUID) -> JobRecord:
        record = self.get_job(job_id)
        validate_transition(record.state, JobState.CONFIRMED)
        missing = record.job_spec.missing_required_fields()
        if missing:
            fields = ", ".join(missing)
            raise DomainConflict(
                f"JobSpec cannot be confirmed until required fields are complete: {fields}"
            )
        now = datetime.now(UTC)
        record.job_spec = record.job_spec.model_copy(
            update={
                "confirmed": True,
                "confirmed_at": now,
                "locked_version": record.job_spec.version,
            },
        )
        record.state = JobState.CONFIRMED
        record.updated_at = now
        return self._repository.save(record)

    def start_calls(self, job_id: UUID) -> JobRecord:
        record = self.get_job(job_id)
        validate_transition(record.state, JobState.CALLING)
        record.state = JobState.CALLING
        record.updated_at = datetime.now(UTC)
        self._repository.save(record)

        calls = self._voice_gateway.create_calls(record.job_spec)
        quotes = [call.outcome.quote for call in calls if call.outcome.quote is not None]
        validate_transition(record.state, JobState.QUOTES_READY)
        record.calls = calls
        record.quotes = quotes
        record.state = JobState.QUOTES_READY
        record.updated_at = datetime.now(UTC)
        return self._repository.save(record)

    def negotiate(self, job_id: UUID) -> JobRecord:
        record = self.get_job(job_id)
        validate_transition(record.state, JobState.NEGOTIATING)
        competitors = [
            quote
            for quote in record.quotes
            if quote.verification_status is VerificationStatus.VERIFIED
        ]
        if not competitors:
            raise DomainConflict("Negotiation requires a verified competing quote")
        verified_competitor = min(
            competitors,
            key=lambda quote: quote.comparable_total or quote.negotiated_total,
        )

        record.state = JobState.NEGOTIATING
        record.updated_at = datetime.now(UTC)
        self._repository.save(record)

        improved = self._negotiation_gateway.negotiate(
            record.job_spec,
            record.quotes,
            verified_competitor,
        )
        if not self._is_improved(improved):
            raise DomainConflict("Negotiation did not measurably improve price or terms")

        recommendation = self._fixtures.load_recommendation().model_copy(
            update={"job_id": record.job_spec.job_id, "generated_at": datetime.now(UTC)},
        )
        validate_transition(record.state, JobState.COMPLETED)
        record.quotes.append(improved)
        record.recommendation = recommendation
        record.state = JobState.COMPLETED
        record.updated_at = datetime.now(UTC)
        return self._repository.save(record)

    def get_report(self, job_id: UUID) -> RecommendationV1:
        record = self.get_job(job_id)
        if record.state is not JobState.COMPLETED or record.recommendation is None:
            raise DomainConflict("Report is available only after negotiation completes")
        return record.recommendation

    def handle_elevenlabs_webhook(self, event: ElevenLabsWebhookEvent) -> WebhookAck:
        accepted = self._repository.record_webhook(
            event.idempotency_key,
            event.model_dump(mode="json"),
        )
        return WebhookAck(accepted=accepted, duplicate=not accepted)

    def discover_vendors(self, origin: str | None, destination: str | None) -> list[Vendor]:
        return self._discovery_gateway.discover(origin, destination)

    @staticmethod
    def _is_improved(quote: QuoteV1) -> bool:
        price_improved = (
            quote.negotiated_total is not None
            and quote.original_total is not None
            and quote.negotiated_total < quote.original_total
        )
        return price_improved or bool(quote.concessions)
