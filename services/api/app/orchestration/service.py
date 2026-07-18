"""Stateful orchestration for the VeraMove intake-to-recommendation lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from services.api.app.contracts import (
    CallStatus,
    ElevenLabsWebhookEvent,
    JobRecord,
    JobSpecV1,
    JobState,
    QuoteV1,
    RecommendationRanking,
    RecommendationV1,
    Vendor,
    WebhookAck,
)
from services.api.app.core.errors import DomainConflict, ResourceNotFound
from services.api.app.core.state_machine import validate_transition
from services.api.app.integrations.tavily.base import VendorDiscoveryGateway
from services.api.app.orchestration.fixtures import DemoFixtures
from services.api.app.orchestration.models import CallAttempt, CallKind, VoiceCallResult
from services.api.app.orchestration.providers import IntelligenceProvider, VoiceProvider
from services.api.app.orchestration.tools import VoiceTools
from services.api.app.repositories.base import (
    CallRepository,
    JobRepository,
    QuoteRepository,
)


def utc_now() -> datetime:
    """Return an aware UTC timestamp for production composition."""

    return datetime.now(UTC)


class VeraMoveService:
    """Coordinate lifecycle state without depending on provider SDKs or persistence details."""

    def __init__(
        self,
        jobs: JobRepository,
        calls: CallRepository,
        quotes: QuoteRepository,
        voice: VoiceProvider,
        intelligence: IntelligenceProvider,
        discovery: VendorDiscoveryGateway,
        fixtures: DemoFixtures,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._jobs = jobs
        self._calls = calls
        self._quotes = quotes
        self._voice = voice
        self._intelligence = intelligence
        self._discovery = discovery
        self._fixtures = fixtures
        self._tools = VoiceTools(calls, quotes, clock=clock)
        self._clock = clock

    def create_job(self, job_spec: JobSpecV1) -> JobRecord:
        if job_spec.confirmed:
            raise DomainConflict("New jobs must be unconfirmed")
        now = self._clock()
        return self._jobs.create(
            JobRecord(
                job_spec=job_spec,
                state=JobState.INTAKE_COMPLETE,
                created_at=now,
                updated_at=now,
            )
        )

    def create_job_from_document(self, document_text: str) -> JobRecord:
        """Extract a fresh structured draft through the intelligence boundary."""

        return self.create_job(self._intelligence.extract_document(document_text))

    def get_job(self, job_id: UUID) -> JobRecord:
        record = self._jobs.get(job_id)
        if record is None:
            raise ResourceNotFound(f"Job {job_id} was not found")
        return record

    def confirm_job(self, job_id: UUID) -> JobRecord:
        record = self.get_job(job_id)
        if record.job_spec.confirmed:
            return record
        validate_transition(record.state, JobState.CONFIRMED)
        now = self._clock()
        record.job_spec = record.job_spec.model_copy(
            update={"confirmed": True, "confirmed_at": now},
            deep=True,
        )
        record.state = JobState.CONFIRMED
        record.updated_at = now
        return self._jobs.save(record)

    def list_call_attempts(self, job_id: UUID) -> list[CallAttempt]:
        self.get_job(job_id)
        return self._calls.list_attempts(job_id)

    def initiate_single_quote_call(
        self,
        job_id: UUID,
        vendor: Vendor,
    ) -> CallAttempt:
        """Persist one attempt before invoking the provider and normalize sync results."""

        record = self.get_job(job_id)
        if not record.job_spec.confirmed:
            raise DomainConflict("Calls require a confirmed JobSpec")

        existing = next(
            (
                attempt
                for attempt in self._calls.list_attempts(job_id)
                if attempt.kind is CallKind.QUOTE
                and attempt.vendor.vendor_id == vendor.vendor_id
                and attempt.job_spec_snapshot.version == record.job_spec.version
            ),
            None,
        )
        if existing is not None:
            return existing

        attempt = self._new_attempt(record, vendor, CallKind.QUOTE)
        result = self._voice.initiate_quote_call(
            attempt.job_spec_snapshot,
            vendor,
            attempt.call_id,
        )
        return self._record_provider_result(attempt, result)

    def initiate_quote_batch(self, job_id: UUID) -> JobRecord:
        """Compose the provider's single-call primitive into an idempotent initial batch."""

        record = self.get_job(job_id)
        if record.state in {
            JobState.CALLING,
            JobState.QUOTES_READY,
            JobState.NEGOTIATING,
            JobState.COMPLETED,
        }:
            return record

        validate_transition(record.state, JobState.CALLING)
        record.state = JobState.CALLING
        record.updated_at = self._clock()
        self._jobs.save(record)

        vendors = self._fixtures.load_vendors()[: self._voice.initial_call_limit]
        for vendor in vendors:
            self.initiate_single_quote_call(job_id, vendor)

        record = self.get_job(job_id)
        if len(self._calls.list_calls(job_id)) == 3:
            validate_transition(record.state, JobState.QUOTES_READY)
            record.state = JobState.QUOTES_READY
            record.updated_at = self._clock()
            record = self._jobs.save(record)
        return record

    def start_calls(self, job_id: UUID) -> JobRecord:
        """Compatibility wrapper for the starter API route."""

        return self.initiate_quote_batch(job_id)

    def initiate_negotiation_call(self, job_id: UUID) -> JobRecord:
        """Negotiate the highest quote using verified same-version leverage."""

        record = self.get_job(job_id)
        if record.state in {JobState.NEGOTIATING, JobState.COMPLETED}:
            return record

        validate_transition(record.state, JobState.NEGOTIATING)
        if not record.quotes:
            raise DomainConflict("Negotiation requires an initial quote")

        target_quote = max(record.quotes, key=lambda quote: quote.negotiated_total)
        competitor = self._tools.get_verified_competing_quote(
            job_id,
            target_quote.vendor.vendor_id,
            record.job_spec.version,
        )
        planned = self._intelligence.negotiate(
            record.job_spec,
            record.quotes,
            competitor,
        )

        record.state = JobState.NEGOTIATING
        record.updated_at = self._clock()
        record = self._jobs.save(record)
        attempt = self._new_attempt(record, target_quote.vendor, CallKind.NEGOTIATION)
        result = self._voice.initiate_negotiation_call(
            attempt.job_spec_snapshot,
            target_quote.vendor,
            competitor,
            planned,
            attempt.call_id,
        )
        attempt = self._record_provider_reference(attempt, result)

        if not self._is_complete(result):
            return self.get_job(job_id)

        assert result.outcome is not None
        assert result.completed_at is not None
        assert result.recording_url is not None
        improved = result.outcome.quote
        if improved is None or not self._is_improved(target_quote, improved):
            raise DomainConflict("Negotiation did not measurably improve price or terms")
        self._tools.save_call_outcome(
            attempt.call_id,
            result.outcome,
            result.completed_at,
            result.recording_url,
        )

        record = self.get_job(job_id)
        record.recommendation = self._build_recommendation(record)
        validate_transition(record.state, JobState.COMPLETED)
        record.state = JobState.COMPLETED
        record.updated_at = self._clock()
        return self._jobs.save(record)

    def negotiate(self, job_id: UUID) -> JobRecord:
        """Compatibility wrapper for the starter API route."""

        return self.initiate_negotiation_call(job_id)

    def get_report(self, job_id: UUID) -> RecommendationV1:
        record = self.get_job(job_id)
        if record.state is not JobState.COMPLETED or record.recommendation is None:
            raise DomainConflict("Report is available only after negotiation completes")
        return record.recommendation

    def handle_elevenlabs_webhook(self, event: ElevenLabsWebhookEvent) -> WebhookAck:
        accepted = self._calls.reserve_webhook(event.idempotency_key)
        return WebhookAck(accepted=accepted, duplicate=not accepted)

    def discover_vendors(self, origin: str | None, destination: str | None) -> list[Vendor]:
        return self._discovery.discover(origin, destination)

    def _new_attempt(
        self,
        record: JobRecord,
        vendor: Vendor,
        kind: CallKind,
    ) -> CallAttempt:
        attempt = CallAttempt(
            call_id=uuid4(),
            job_id=record.job_spec.job_id,
            kind=kind,
            vendor=vendor.model_copy(deep=True),
            job_spec_snapshot=record.job_spec.model_copy(deep=True),
            status=CallStatus.PENDING,
            started_at=self._clock(),
        )
        return self._calls.create_attempt(attempt)

    def _record_provider_result(
        self,
        attempt: CallAttempt,
        result: VoiceCallResult,
    ) -> CallAttempt:
        attempt = self._record_provider_reference(attempt, result)
        if self._is_complete(result):
            assert result.outcome is not None
            assert result.completed_at is not None
            assert result.recording_url is not None
            self._tools.save_call_outcome(
                attempt.call_id,
                result.outcome,
                result.completed_at,
                result.recording_url,
            )
        return self._calls.get_attempt(attempt.call_id) or attempt

    def _record_provider_reference(
        self,
        attempt: CallAttempt,
        result: VoiceCallResult,
    ) -> CallAttempt:
        in_progress = attempt.model_copy(
            update={"status": CallStatus.IN_PROGRESS, "reference": result.reference},
            deep=True,
        )
        return self._calls.save_attempt(in_progress)

    def _build_recommendation(self, record: JobRecord) -> RecommendationV1:
        template = self._fixtures.load_recommendation()
        evidence = [
            item
            for quote in record.quotes
            for item in quote.transcript_evidence
        ]
        quotes_by_id = {quote.quote_id: quote for quote in record.quotes}
        quotes_by_vendor: dict[UUID, list[QuoteV1]] = {}
        for quote in record.quotes:
            quotes_by_vendor.setdefault(quote.vendor.vendor_id, []).append(quote)

        rankings: list[RecommendationRanking] = []
        for ranking in template.rankings:
            quote = quotes_by_id.get(ranking.quote_id)
            if quote is None:
                candidates = quotes_by_vendor.get(ranking.vendor.vendor_id, [])
                quote = min(candidates, key=lambda item: item.negotiated_total, default=None)
            if quote is None:
                continue
            vendor_evidence = [
                item
                for vendor_quote in quotes_by_vendor[quote.vendor.vendor_id]
                for item in vendor_quote.transcript_evidence
            ]
            rankings.append(
                ranking.model_copy(
                    update={
                        "vendor": quote.vendor,
                        "quote_id": quote.quote_id,
                        "total": quote.negotiated_total,
                        "evidence_ids": [item.evidence_id for item in vendor_evidence],
                    },
                    deep=True,
                )
            )

        return template.model_copy(
            update={
                "job_id": record.job_spec.job_id,
                "generated_at": self._clock(),
                "rankings": rankings,
                "evidence_ids": [item.evidence_id for item in evidence],
                "transcript_evidence": evidence,
            },
            deep=True,
        )

    @staticmethod
    def _is_complete(result: VoiceCallResult) -> bool:
        return (
            result.outcome is not None
            and result.recording_url is not None
            and result.completed_at is not None
        )

    @staticmethod
    def _is_improved(initial: QuoteV1, negotiated: QuoteV1) -> bool:
        return (
            negotiated.negotiated_total < initial.negotiated_total
            or bool(negotiated.concessions)
        )
