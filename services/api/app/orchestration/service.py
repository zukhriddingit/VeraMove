"""Stateful orchestration for the VeraMove intake-to-recommendation lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from services.api.app.contracts import (
    CallOutcome,
    CallOutcomeType,
    CallStatus,
    JobRecord,
    JobSpecV1,
    JobState,
    QuoteV1,
    RecommendationRanking,
    RecommendationV1,
    Vendor,
    WebhookAck,
)
from services.api.app.core.errors import (
    DomainConflict,
    DomainError,
    ProviderConfigurationError,
    ProviderRequestError,
    ResourceNotFound,
)
from services.api.app.core.state_machine import validate_transition
from services.api.app.integrations.elevenlabs.webhook import (
    ElevenLabsWebhookProcessor,
)
from services.api.app.integrations.tavily.base import VendorDiscoveryGateway
from services.api.app.intelligence.ranking import RecommendationNarrator
from services.api.app.orchestration.fixtures import DemoFixtures
from services.api.app.orchestration.models import (
    CallAttempt,
    CallKind,
    JobEvent,
    NegotiationContext,
    VoiceCallResult,
)
from services.api.app.orchestration.providers import IntelligenceProvider, VoiceProvider
from services.api.app.orchestration.role_play import DiscoveryVendorRoster, VendorRoster
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
        webhooks: ElevenLabsWebhookProcessor,
        fixtures: DemoFixtures,
        vendor_roster: VendorRoster | None = None,
        recommendation_narrator: RecommendationNarrator | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._jobs = jobs
        self._calls = calls
        self._quotes = quotes
        self._voice = voice
        self._intelligence = intelligence
        self._discovery = discovery
        self._vendor_roster = vendor_roster
        self._webhooks = webhooks
        self._fixtures = fixtures
        self._recommendation_narrator = recommendation_narrator
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
        missing = record.job_spec.missing_required_fields()
        if missing:
            fields = ", ".join(missing)
            raise DomainConflict(
                f"JobSpec cannot be confirmed until required fields are complete: {fields}"
            )
        now = self._clock()
        record.job_spec = record.job_spec.model_copy(
            update={
                "confirmed": True,
                "confirmed_at": now,
                "locked_version": record.job_spec.version,
            },
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
        destination_slot: Literal[0, 1, 2] = 0,
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

        attempt = self._new_attempt(
            record,
            vendor,
            CallKind.QUOTE,
            destination_slot=destination_slot,
        )
        try:
            result = self._voice.initiate_quote_call(
                attempt.job_spec_snapshot,
                vendor,
                attempt.call_id,
                attempt.destination_slot,
            )
        except ProviderRequestError:
            self._record_provider_failure(attempt)
            return self._calls.get_attempt(attempt.call_id) or attempt
        except DomainError:
            self._record_unexpected_failure(attempt)
            raise
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
        vendors = self._initial_vendors(record)
        record.state = JobState.CALLING
        record.updated_at = self._clock()
        self._jobs.save(record)

        initial_vendors = vendors[: self._voice.initial_call_limit]
        attempts: list[CallAttempt] = []
        for destination_slot, vendor in enumerate(initial_vendors):
            existing = next(
                (
                    attempt
                    for attempt in self._calls.list_attempts(job_id)
                    if attempt.kind is CallKind.QUOTE
                    and attempt.vendor.vendor_id == vendor.vendor_id
                    and attempt.job_spec_version == record.job_spec.version
                ),
                None,
            )
            attempts.append(
                existing
                or self._new_attempt(
                    record,
                    vendor,
                    CallKind.QUOTE,
                    destination_slot=destination_slot,
                )
            )

        for attempt in attempts:
            if attempt.status is not CallStatus.PENDING:
                continue
            try:
                result = self._voice.initiate_quote_call(
                    attempt.job_spec_snapshot,
                    attempt.vendor,
                    attempt.call_id,
                    attempt.destination_slot,
                )
            except ProviderRequestError:
                self._record_provider_failure(attempt)
                continue
            except DomainError:
                self._record_unexpected_failure(attempt)
                raise
            self._record_provider_result(attempt, result)

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
        priced_quotes = [
            (quote, total)
            for quote in record.quotes
            if (total := self._quote_total(quote)) is not None
        ]
        if not priced_quotes:
            raise DomainConflict("Negotiation requires an initial quote with a comparable total")

        target_quote = max(priced_quotes, key=lambda item: item[1])[0]
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
        target_attempt = next(
            (
                item
                for item in self._calls.list_attempts(job_id)
                if item.kind is CallKind.QUOTE
                and item.vendor.vendor_id == target_quote.vendor.vendor_id
                and item.job_spec_version == record.job_spec.version
            ),
            None,
        )
        if target_attempt is None:
            raise DomainConflict("Negotiation target has no initial call slot")
        leverage_total = (
            competitor.comparable_total
            if competitor.comparable_total is not None
            else competitor.negotiated_total
        )
        if leverage_total is None:
            raise DomainConflict("Verified competitor has no comparable total")
        attempt = self._new_attempt(
            record,
            target_quote.vendor,
            CallKind.NEGOTIATION,
            destination_slot=target_attempt.destination_slot,
            negotiation_context=NegotiationContext(
                target_quote_id=target_quote.quote_id,
                competitor_quote_id=competitor.quote_id,
                eligible_leverage_total=leverage_total,
                evidence_ids=tuple(
                    evidence.evidence_id for evidence in competitor.transcript_evidence
                ),
            ),
        )
        try:
            result = self._voice.initiate_negotiation_call(
                attempt.job_spec_snapshot,
                target_quote.vendor,
                competitor,
                planned,
                attempt.call_id,
                attempt.destination_slot,
            )
        except (ProviderConfigurationError, ProviderRequestError):
            self._record_provider_failure(attempt)
            raise
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

    def handle_elevenlabs_webhook(
        self,
        raw_body: bytes,
        signature_header: str | None,
    ) -> WebhookAck:
        """Authenticate raw provider bytes and apply their safe normalized event."""

        event = self._webhooks.process(raw_body, signature_header)
        if not self._calls.reserve_webhook(event.idempotency_key):
            return WebhookAck(accepted=False, duplicate=True)
        attempt = self._calls.get_attempt(event.call_id) if event.call_id else None
        if attempt is None and event.conversation_id:
            attempt = self._calls.find_attempt_by_conversation_id(event.conversation_id)
        if attempt and event.call_status:
            attempt = attempt.model_copy(
                update={
                    "status": event.call_status,
                    "completed_at": (
                        event.event_timestamp
                        if event.call_status in {CallStatus.COMPLETED, CallStatus.FAILED}
                        else None
                    ),
                }
            )
            self._calls.save_attempt(attempt)
        if attempt:
            self._calls.append_event(
                JobEvent(
                    job_id=attempt.job_id,
                    call_id=attempt.call_id,
                    event_type=event.event_type,
                    occurred_at=event.event_timestamp,
                    metadata={"provider_status": event.provider_status},
                )
            )
        return WebhookAck(accepted=True, duplicate=False)

    def get_events(self, job_id: UUID) -> list[JobEvent]:
        """Return safe normalized events after verifying the job exists."""

        self.get_job(job_id)
        return self._calls.list_events(job_id)

    def discover_vendors(self, origin: str | None, destination: str | None) -> list[Vendor]:
        return self._discovery.discover(origin, destination)

    @property
    def vendor_discovery_source(self) -> Literal["synthetic_mock", "tavily"]:
        return self._discovery.source

    def _initial_vendors(self, record: JobRecord) -> list[Vendor]:
        roster = self._vendor_roster or DiscoveryVendorRoster(self._discovery)
        candidates = roster.initial_vendors(record.job_spec)
        distinct: dict[UUID, Vendor] = {}
        for vendor in candidates:
            distinct.setdefault(vendor.vendor_id, vendor)
        if len(distinct) < 3:
            raise DomainConflict("Initial calling requires three distinct vendors")
        return list(distinct.values())[:3]

    def _new_attempt(
        self,
        record: JobRecord,
        vendor: Vendor,
        kind: CallKind,
        destination_slot: Literal[0, 1, 2],
        negotiation_context: NegotiationContext | None = None,
    ) -> CallAttempt:
        attempt = CallAttempt(
            call_id=uuid4(),
            job_id=record.job_spec.job_id,
            kind=kind,
            vendor=vendor.model_copy(deep=True),
            job_spec_snapshot=record.job_spec.model_copy(deep=True),
            destination_slot=destination_slot,
            expected_agent_id=getattr(
                self._voice,
                "outbound_agent_id",
                "synthetic-provider-outbound-agent",
            ),
            agent_config_version=getattr(
                self._voice,
                "agent_config_version",
                "provider-v1",
            ),
            negotiation_context=negotiation_context,
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

    def _record_provider_failure(self, attempt: CallAttempt) -> None:
        """Preserve a supported non-quote failure and allow sibling slots to continue."""

        failed_at = self._clock()
        self._tools.save_call_outcome(
            attempt.call_id,
            CallOutcome(
                type=CallOutcomeType.FAILED,
                reason="The voice provider rejected or could not initiate the call.",
            ),
            failed_at,
            None,
        )

    def _record_unexpected_failure(self, attempt: CallAttempt) -> None:
        """Make a visible validation/programming failure explicit without inventing an outcome."""

        failed_at = self._clock()
        self._calls.save_attempt(
            attempt.model_copy(
                update={"status": CallStatus.FAILED, "completed_at": failed_at},
                deep=True,
            )
        )
        record = self.get_job(attempt.job_id)
        record.state = JobState.FAILED
        record.updated_at = failed_at
        self._jobs.save(record)

    def _build_recommendation(self, record: JobRecord) -> RecommendationV1:
        template = self._fixtures.load_recommendation()
        evidence = [item for quote in record.quotes for item in quote.transcript_evidence]
        quotes_by_id = {quote.quote_id: quote for quote in record.quotes}
        quotes_by_vendor: dict[UUID, list[QuoteV1]] = {}
        for quote in record.quotes:
            quotes_by_vendor.setdefault(quote.vendor.vendor_id, []).append(quote)

        rankings: list[RecommendationRanking] = []
        for ranking in template.rankings:
            quote = quotes_by_id.get(ranking.quote_id)
            if quote is None:
                candidates = [
                    (item, total)
                    for item in quotes_by_vendor.get(ranking.vendor.vendor_id, [])
                    if (total := self._quote_total(item)) is not None
                ]
                quote = min(candidates, key=lambda item: item[1], default=(None, None))[0]
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
                        "total": self._quote_total(quote),
                        "evidence_ids": [item.evidence_id for item in vendor_evidence],
                    },
                    deep=True,
                )
            )

        uses_discovered_vendors = len(rankings) != len(quotes_by_vendor)
        if uses_discovered_vendors:
            rankings = self._rank_discovered_vendors(quotes_by_vendor)

        winner = rankings[0]
        priced_rankings = [item for item in rankings if item.total is not None]
        cheapest = min(priced_rankings, key=lambda item: item.total, default=None)
        summary = template.summary
        hidden_fee_findings = template.hidden_fee_findings
        assumptions = template.assumptions
        uncertainty = template.uncertainty
        if uses_discovered_vendors:
            summary = (
                f"{winner.vendor.name} is the strongest evidence-backed role-play option "
                "after comparing verified totals and documented concessions."
            )
            hidden_fee_findings = []
            assumptions = [
                "Discovered companies are represented only by synthetic role-play outcomes."
            ]
            uncertainty = ["Role-play prices and availability are not claims about real companies."]

        recommendation = template.model_copy(
            update={
                "recommendation_id": uuid5(
                    NAMESPACE_URL,
                    f"recommendation:{record.job_spec.job_id}:{record.job_spec.version}",
                ),
                "job_id": record.job_spec.job_id,
                "generated_at": self._clock(),
                "summary": summary,
                "winning_vendor_id": winner.vendor.vendor_id,
                "cheapest_vendor_id": (cheapest.vendor.vendor_id if cheapest is not None else None),
                "best_value_vendor_id": winner.vendor.vendor_id,
                "rankings": rankings,
                "evidence_ids": [item.evidence_id for item in evidence],
                "transcript_evidence": evidence,
                "assumptions": assumptions,
                "uncertainty": uncertainty,
                "hidden_fee_findings": hidden_fee_findings,
            },
            deep=True,
        )
        if self._recommendation_narrator is not None:
            summary = self._recommendation_narrator.explain(
                record.job_spec,
                recommendation.rankings,
                recommendation.hidden_fee_findings,
            )
            recommendation = recommendation.model_copy(
                update={"summary": summary},
                deep=True,
            )
        return recommendation

    @classmethod
    def _rank_discovered_vendors(
        cls,
        quotes_by_vendor: dict[UUID, list[QuoteV1]],
    ) -> list[RecommendationRanking]:
        selected: list[tuple[QuoteV1, Decimal | None, list]] = []
        for vendor_quotes in quotes_by_vendor.values():
            quote = min(
                vendor_quotes,
                key=lambda item: (
                    cls._quote_total(item) is None,
                    cls._quote_total(item) or Decimal("Infinity"),
                ),
            )
            evidence = [
                item for vendor_quote in vendor_quotes for item in vendor_quote.transcript_evidence
            ]
            selected.append((quote, cls._quote_total(quote), evidence))
        selected.sort(
            key=lambda item: (
                item[1] is None,
                item[1] or Decimal("Infinity"),
                item[0].vendor.slug,
            )
        )
        return [
            RecommendationRanking(
                rank=rank,
                vendor=quote.vendor,
                quote_id=quote.quote_id,
                total=total,
                rationale=[
                    (
                        f"Comparable synthetic total: {total} USD."
                        if total is not None
                        else "Comparable synthetic total is unknown."
                    ),
                    f"Binding status: {quote.binding_type.value}.",
                    f"{len(evidence)} transcript evidence item(s) support this ranking.",
                    *(
                        [f"{len(quote.concessions)} documented concession(s)."]
                        if quote.concessions
                        else []
                    ),
                ],
                red_flags=[
                    *quote.red_flags,
                    *(finding.description for finding in quote.findings),
                ],
                evidence_ids=[item.evidence_id for item in evidence],
            )
            for rank, (quote, total, evidence) in enumerate(selected, start=1)
        ]

    @staticmethod
    def _is_complete(result: VoiceCallResult) -> bool:
        return (
            result.outcome is not None
            and result.recording_url is not None
            and result.completed_at is not None
        )

    @staticmethod
    def _is_improved(initial: QuoteV1, negotiated: QuoteV1) -> bool:
        initial_total = VeraMoveService._quote_total(initial)
        negotiated_total = VeraMoveService._quote_total(negotiated)
        price_improved = (
            initial_total is not None
            and negotiated_total is not None
            and negotiated_total < initial_total
        )
        return price_improved or bool(negotiated.concessions)

    @staticmethod
    def _quote_total(quote: QuoteV1) -> Decimal | None:
        """Prefer Member 2's comparable total, falling back to negotiated total."""

        if quote.comparable_total is not None:
            return quote.comparable_total
        return quote.negotiated_total
