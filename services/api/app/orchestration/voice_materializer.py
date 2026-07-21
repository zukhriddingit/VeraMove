"""Canonicalize authenticated ElevenLabs results without retaining provider envelopes."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import HttpUrl, ValidationError

from services.api.app.contracts import (
    CallOutcome,
    CallOutcomeType,
    CallRecord,
    CallStatus,
    DataClassification,
    DwellingType,
    FeeCategory,
    IntakeSource,
    InventoryItem,
    JobRecord,
    JobSpecV1,
    JobState,
    MovingServices,
    OriginDestinationAccess,
    QuoteV1,
    RecommendationV1,
    WebhookAck,
)
from services.api.app.core.errors import DomainConflict, ResourceNotFound
from services.api.app.core.state_machine import validate_transition
from services.api.app.integrations.elevenlabs.analysis import INTAKE_COLLECTION_FIELDS
from services.api.app.integrations.elevenlabs.models import (
    VerifiedCallInitiationFailure,
    VerifiedElevenLabsEvent,
    VerifiedPostCallTranscription,
)
from services.api.app.intelligence.quotes import is_measurable_quote_improvement
from services.api.app.intelligence.ranking import is_quote_eligible
from services.api.app.orchestration.intake_sessions import (
    IntakeDataMode,
    IntakeSession,
    IntakeSessionStatus,
)
from services.api.app.orchestration.models import CallAttempt, CallKind, JobEvent
from services.api.app.orchestration.outbound_materializer import materialize_outbound_event
from services.api.app.orchestration.providers import QuoteVerificationGateway
from services.api.app.orchestration.recording_capability import RecordingCapabilitySigner
from services.api.app.orchestration.tools import VoiceTools
from services.api.app.repositories.base import (
    CallRepository,
    IntakeSessionRepository,
    JobRepository,
    QuoteRepository,
    VoiceIntakeCompletion,
    VoiceIntakeFailure,
    VoiceIntakeIncomplete,
    VoiceMaterializationRepository,
    VoiceWebhookLease,
    VoiceWebhookMaterialization,
)

# Leave enough headroom for the bounded OpenAI recommendation narration request
# and the final atomic persistence call. Provider retries can reclaim the lease
# after this interval if the worker exits before finalization.
VOICE_WEBHOOK_LEASE_SECONDS = 120
MAX_INTAKE_LIST_ITEMS = 200
MAX_SPECIAL_ITEM_LENGTH = 300
_REDACTED_CITY_STATE = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,98}, [A-Z]{2}$")
_INTAKE_CONTROL_FIELDS = frozenset({"recording_consent", "summary_confirmed"})


class VoiceMaterializer:
    """Route one verified event into an intake or outbound canonical write."""

    def __init__(
        self,
        *,
        jobs: JobRepository,
        calls: CallRepository,
        quotes: QuoteRepository,
        intake_sessions: IntakeSessionRepository,
        materialization_repository: VoiceMaterializationRepository,
        tools: VoiceTools,
        verifier: QuoteVerificationGateway,
        recording_signer: RecordingCapabilitySigner | None,
        required_fee_categories: set[FeeCategory],
        recommendation_builder: Callable[[JobRecord], RecommendationV1],
        clock: Callable[[], datetime],
    ) -> None:
        self._jobs = jobs
        self._calls = calls
        self._quotes = quotes
        self._intake_sessions = intake_sessions
        self._materialization_repository = materialization_repository
        self._tools = tools
        self._verifier = verifier
        self._recording_signer = recording_signer
        self._required_fee_categories = set(required_fee_categories)
        self._recommendation_builder = recommendation_builder
        self._clock = clock

    def materialize(self, event: VerifiedElevenLabsEvent) -> WebhookAck:
        """Materialize one authenticated provider event exactly once."""

        if isinstance(event, VerifiedCallInitiationFailure):
            return self._materialize_initiation_failure(event)
        if event.dynamic_variables.intake_session_id is not None:
            return self._materialize_intake(event)
        return self._materialize_outbound(event)

    def _materialize_outbound(self, event: VerifiedPostCallTranscription) -> WebhookAck:
        attempt = self._require_attempt(event.conversation_id)
        if self._canonical_call_exists(attempt):
            return WebhookAck(accepted=False, duplicate=True)
        lease_token, duplicate = self._claim(event.idempotency_key, event.event_type)
        if duplicate is not None:
            return duplicate
        assert lease_token is not None
        try:
            consented_event = event.model_copy(
                update={
                    "has_audio": (
                        event.has_audio and event.collected_data.get("recording_consent") is True
                    )
                },
                deep=True,
            )
            recording_url = self._recording_url(consented_event, attempt)
            materialized = materialize_outbound_event(
                event=consented_event,
                attempt=attempt,
                recording_url=recording_url,
                verifier=self._verifier,
                required_fee_categories=self._required_fee_categories,
            )
            if attempt.kind is CallKind.NEGOTIATION:
                self._validate_negotiation_result(attempt, materialized.outcome)
            canonical = self._build_outbound_materialization(
                event=event,
                attempt=attempt,
                outcome=materialized.outcome,
                recording_url=materialized.recording_url,
                provider_version_id=materialized.provider_version_id,
            )
        except DomainConflict:
            self._fail_receipt(
                event.idempotency_key,
                lease_token,
                "invalid_voice_materialization",
                retryable=False,
            )
            raise
        try:
            finalized = self._materialization_repository.finalize_voice_webhook(
                event.idempotency_key,
                lease_token,
                canonical,
                self._clock(),
            )
        except Exception:
            self._fail_receipt(
                event.idempotency_key,
                lease_token,
                "voice_finalize_failed",
                retryable=True,
            )
            raise
        return WebhookAck(accepted=not finalized.duplicate, duplicate=finalized.duplicate)

    def _materialize_intake(self, event: VerifiedPostCallTranscription) -> WebhookAck:
        session = self._require_intake_session(event)
        existing = self._jobs.get(session.job_id)
        if session.status is IntakeSessionStatus.COMPLETED:
            if existing is None:
                raise DomainConflict("Completed intake session has no canonical JobRecord")
            return WebhookAck(accepted=False, duplicate=True)
        if session.status in {
            IntakeSessionStatus.INCOMPLETE,
            IntakeSessionStatus.FAILED,
        }:
            return WebhookAck(accepted=False, duplicate=True)

        lease_token, duplicate = self._claim(event.idempotency_key, event.event_type)
        if duplicate is not None:
            return duplicate
        assert lease_token is not None
        try:
            if existing is not None:
                raise DomainConflict("Intake session already owns a canonical JobSpec")
            if event.collected_data.get("recording_consent") is not True:
                canonical = _failed_intake_materialization(
                    session,
                    event,
                    "consent_unavailable",
                )
            elif not (
                session.base_job_spec is not None
                or _has_collected_move_fact(event.collected_data)
            ):
                canonical = _failed_intake_materialization(
                    session,
                    event,
                    "no_move_facts",
                )
            else:
                collected = _intake_job_spec(event, session, require_summary=False)
                job_spec = _merge_intake_specs(
                    session.base_job_spec,
                    collected,
                    event.collected_data,
                )
                missing_fields = tuple(job_spec.missing_required_fields())
                if (
                    event.collected_data.get("summary_confirmed") is True
                    and not missing_fields
                ):
                    canonical = _completed_intake_materialization(
                        session,
                        event,
                        job_spec,
                    )
                else:
                    canonical = VoiceIntakeIncomplete(
                        session=session.model_copy(
                            update={
                                "conversation_id": event.conversation_id,
                                "status": IntakeSessionStatus.INCOMPLETE,
                                "partial_job_spec": job_spec,
                                "missing_fields": missing_fields,
                                "terminal_reason": (
                                    "missing_required_fields"
                                    if event.collected_data.get("summary_confirmed") is True
                                    else "user_ended_before_summary"
                                ),
                                "updated_at": event.event_timestamp,
                            },
                            deep=True,
                        ),
                        event_type=event.event_type,
                    )
        except (DomainConflict, ValidationError):
            self._fail_receipt(
                event.idempotency_key,
                lease_token,
                "invalid_voice_intake",
                retryable=False,
            )
            raise
        try:
            finalized = self._materialization_repository.finalize_voice_intake_webhook(
                event.idempotency_key,
                lease_token,
                canonical,
                self._clock(),
            )
        except Exception:
            self._fail_receipt(
                event.idempotency_key,
                lease_token,
                "voice_intake_finalize_failed",
                retryable=True,
            )
            raise
        return WebhookAck(accepted=not finalized.duplicate, duplicate=finalized.duplicate)

    def _materialize_initiation_failure(
        self,
        event: VerifiedCallInitiationFailure,
    ) -> WebhookAck:
        attempt = self._calls.find_attempt_by_conversation_id(event.conversation_id)
        if attempt is not None:
            if event.agent_id != attempt.expected_agent_id:
                raise DomainConflict("Voice event correlation mismatch: agent")
            if self._canonical_call_exists(attempt):
                return WebhookAck(accepted=False, duplicate=True)
            return self._materialize_failed_attempt(
                attempt,
                idempotency_key=event.idempotency_key,
                event_type=event.event_type,
                completed_at=event.event_timestamp,
                reason=f"Voice call initiation failed: {event.failure_reason}.",
            )

        session = self._intake_sessions.find_intake_session_by_conversation_id(
            event.conversation_id
        )
        if session is None:
            raise ResourceNotFound("Voice initiation failure could not be correlated")
        if event.agent_id != session.expected_agent_id:
            raise DomainConflict("Voice event correlation mismatch: agent")
        if session.status is IntakeSessionStatus.FAILED:
            return WebhookAck(accepted=False, duplicate=True)
        if session.status is IntakeSessionStatus.COMPLETED:
            raise DomainConflict("Completed intake session cannot fail initiation")
        lease_token, duplicate = self._claim(event.idempotency_key, event.event_type)
        if duplicate is not None:
            return duplicate
        assert lease_token is not None
        try:
            canonical = VoiceIntakeFailure(
                session=session.model_copy(
                    update={
                        "status": IntakeSessionStatus.FAILED,
                        "failure_code": f"provider_{event.failure_reason.replace('-', '_')}",
                        "updated_at": event.event_timestamp,
                    },
                    deep=True,
                ),
                event_type=event.event_type,
            )
        except ValidationError:
            self._fail_receipt(
                event.idempotency_key,
                lease_token,
                "invalid_voice_intake_failure",
                retryable=False,
            )
            raise
        try:
            finalized = self._materialization_repository.finalize_voice_intake_webhook(
                event.idempotency_key,
                lease_token,
                canonical,
                self._clock(),
            )
        except Exception:
            self._fail_receipt(
                event.idempotency_key,
                lease_token,
                "voice_intake_finalize_failed",
                retryable=True,
            )
            raise
        return WebhookAck(accepted=not finalized.duplicate, duplicate=finalized.duplicate)

    def _require_attempt(self, conversation_id: str) -> CallAttempt:
        attempt = self._calls.find_attempt_by_conversation_id(conversation_id)
        if attempt is None:
            raise ResourceNotFound("Voice conversation has no stored call attempt")
        return attempt

    def _require_intake_session(
        self,
        event: VerifiedPostCallTranscription,
    ) -> IntakeSession:
        variables = event.dynamic_variables
        assert variables.intake_session_id is not None
        session = self._intake_sessions.get_intake_session(variables.intake_session_id)
        if session is None:
            raise ResourceNotFound("Voice intake session was not found")
        mismatches = {
            "provider_status": (
                event.provider_status != "done" or event.call_status is not CallStatus.COMPLETED
            ),
            "agent": event.agent_id != session.expected_agent_id,
            "conversation": (
                session.conversation_id is not None
                and event.conversation_id != session.conversation_id
            ),
            "job": variables.job_id != session.job_id,
            "agent_config": variables.agent_config_version != session.agent_config_version,
            "outbound_call": variables.call_id is not None,
            "outbound_vendor": variables.vendor_id is not None,
            "outbound_mode": variables.call_mode is not None,
            "outbound_version": variables.job_spec_version is not None,
            "outbound_snapshot": variables.job_spec_sha256 is not None,
        }
        failed = [name for name, mismatch in mismatches.items() if mismatch]
        if failed:
            raise DomainConflict("Voice intake correlation mismatch: " + ", ".join(failed))
        unexpected = set(event.collected_data) - INTAKE_COLLECTION_FIELDS
        if unexpected:
            raise DomainConflict(
                "Voice intake contains outbound fields: " + ", ".join(sorted(unexpected))
            )
        return session

    def _recording_url(
        self,
        event: VerifiedPostCallTranscription,
        attempt: CallAttempt,
    ) -> HttpUrl:
        if self._recording_signer is not None:
            return self._recording_signer.build_url(attempt.call_id, attempt.job_id)
        if event.has_audio:
            raise DomainConflict("Live recording capability is not configured")
        return HttpUrl(f"https://no-audio.invalid/{attempt.call_id}")

    def _canonical_call_exists(self, attempt: CallAttempt) -> bool:
        return any(
            call.call_id == attempt.call_id for call in self._calls.list_calls(attempt.job_id)
        )

    def materialize_failed_repair(
        self,
        attempt: CallAttempt,
        *,
        idempotency_key: str,
        failure_code: str,
    ) -> WebhookAck:
        """Route a typed failed-conversation repair through the normal finalizer."""

        stored = self._calls.get_attempt(attempt.call_id)
        if stored is None or stored != attempt:
            raise DomainConflict("Voice repair attempt does not match repository state")
        return self._materialize_failed_attempt(
            stored,
            idempotency_key=idempotency_key,
            event_type=failure_code,
            completed_at=self._clock(),
            reason="The provider conversation ended in a failed state.",
        )

    def _materialize_failed_attempt(
        self,
        attempt: CallAttempt,
        *,
        idempotency_key: str,
        event_type: str,
        completed_at: datetime,
        reason: str,
    ) -> WebhookAck:
        if self._canonical_call_exists(attempt):
            return WebhookAck(accepted=False, duplicate=True)
        lease_token, duplicate = self._claim(idempotency_key, event_type)
        if duplicate is not None:
            return duplicate
        assert lease_token is not None
        try:
            canonical = self._build_outbound_materialization(
                event=None,
                attempt=attempt,
                outcome=CallOutcome(type=CallOutcomeType.FAILED, reason=reason),
                recording_url=None,
                provider_version_id=None,
                event_type=event_type,
                completed_at=completed_at,
            )
        except DomainConflict:
            self._fail_receipt(
                idempotency_key,
                lease_token,
                "invalid_voice_failure",
                retryable=False,
            )
            raise
        try:
            finalized = self._materialization_repository.finalize_voice_webhook(
                idempotency_key,
                lease_token,
                canonical,
                self._clock(),
            )
        except Exception:
            self._fail_receipt(
                idempotency_key,
                lease_token,
                "voice_finalize_failed",
                retryable=True,
            )
            raise
        return WebhookAck(accepted=not finalized.duplicate, duplicate=finalized.duplicate)

    def _build_outbound_materialization(
        self,
        *,
        event: VerifiedPostCallTranscription | None,
        attempt: CallAttempt,
        outcome: CallOutcome,
        recording_url: HttpUrl | None,
        provider_version_id: str | None,
        event_type: str | None = None,
        completed_at: datetime | None = None,
    ) -> VoiceWebhookMaterialization:
        terminal_at = completed_at or (event.event_timestamp if event is not None else None)
        if terminal_at is None or terminal_at < attempt.started_at:
            raise DomainConflict("Call completion cannot precede call start")
        status = (
            CallStatus.FAILED if outcome.type is CallOutcomeType.FAILED else CallStatus.COMPLETED
        )
        terminal_attempt = attempt.model_copy(
            update={
                "status": status,
                "completed_at": terminal_at,
                "provider_version_id": provider_version_id,
            },
            deep=True,
        )
        quote = outcome.quote
        if quote is not None:
            self._tools._validate_quote(terminal_attempt, quote)
        call = CallRecord(
            call_id=attempt.call_id,
            job_id=attempt.job_id,
            vendor=attempt.vendor,
            status=status,
            started_at=attempt.started_at,
            completed_at=terminal_at,
            outcome=outcome,
            recording_url=recording_url,
        )
        expected_revision = self._materialization_repository.get_job_revision(attempt.job_id)
        record = self._require_job(attempt.job_id).model_copy(deep=True)
        record.calls = [item for item in record.calls if item.call_id != call.call_id]
        record.calls.append(call)
        if quote is not None:
            record.quotes = [item for item in record.quotes if item.quote_id != quote.quote_id]
            record.quotes.append(quote)
        record.updated_at = max(record.updated_at, terminal_at)
        if attempt.kind is CallKind.QUOTE:
            self._advance_initial_candidate(record, attempt.job_spec_version)
        elif outcome.type is CallOutcomeType.ITEMIZED_QUOTE:
            if record.state is not JobState.NEGOTIATING:
                raise DomainConflict("Negotiation result arrived outside negotiation state")
            record.recommendation = self._recommendation_builder(record)
            validate_transition(record.state, JobState.COMPLETED)
            record.state = JobState.COMPLETED
        else:
            if record.state is not JobState.NEGOTIATING:
                raise DomainConflict("Negotiation result arrived outside negotiation state")
            validate_transition(record.state, JobState.FAILED)
            record.state = JobState.FAILED
        safe_event_type = event_type or (event.event_type if event is not None else None)
        if safe_event_type is None:
            raise DomainConflict("Voice materialization event type is missing")
        job_event = JobEvent(
            event_id=uuid5(NAMESPACE_URL, f"voice-event:{safe_event_type}:{attempt.call_id}"),
            job_id=attempt.job_id,
            call_id=attempt.call_id,
            event_type=safe_event_type,
            occurred_at=terminal_at,
            metadata={
                "provider_status": (event.provider_status if event is not None else "failed")
            },
        )
        return VoiceWebhookMaterialization(
            attempt=terminal_attempt,
            call=call,
            quote=quote,
            job=record,
            event=job_event,
            expected_revision=expected_revision,
        )

    def _advance_initial_candidate(
        self,
        record: JobRecord,
        job_spec_version: str,
    ) -> None:
        attempts = [
            attempt
            for attempt in self._calls.list_attempts(record.job_spec.job_id)
            if attempt.kind is CallKind.QUOTE and attempt.job_spec_version == job_spec_version
        ]
        if len(attempts) != 3:
            return
        canonical_call_ids = {call.call_id for call in record.calls}
        if any(attempt.call_id not in canonical_call_ids for attempt in attempts):
            return
        if record.state is JobState.CALLING:
            validate_transition(record.state, JobState.QUOTES_READY)
            record.state = JobState.QUOTES_READY

    def _claim(
        self,
        idempotency_key: str,
        event_type: str,
    ) -> tuple[UUID | None, WebhookAck | None]:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            now = now.replace(tzinfo=UTC)
        lease_token = uuid4()
        claim = self._materialization_repository.claim_voice_webhook_receipt(
            VoiceWebhookLease(
                idempotency_key=idempotency_key,
                event_type=event_type,
                lease_token=lease_token,
                lease_expires_at=now + timedelta(seconds=VOICE_WEBHOOK_LEASE_SECONDS),
                now=now,
            )
        )
        if claim.claimed:
            return lease_token, None
        return None, WebhookAck(accepted=False, duplicate=True)

    def _fail_receipt(
        self,
        idempotency_key: str,
        lease_token: UUID,
        failure_code: str,
        *,
        retryable: bool,
    ) -> None:
        self._materialization_repository.fail_voice_webhook_receipt(
            idempotency_key,
            lease_token,
            failure_code,
            retryable,
            self._clock(),
        )

    def _validate_negotiation_result(
        self,
        attempt: CallAttempt,
        outcome: CallOutcome,
    ) -> None:
        if outcome.type is not CallOutcomeType.ITEMIZED_QUOTE:
            return
        improved = outcome.quote
        context = attempt.negotiation_context
        if improved is None or context is None:
            raise DomainConflict("Negotiation result lacks stored verification context")
        quotes = self._quotes.list_quotes(attempt.job_id)
        target = next(
            (quote for quote in quotes if quote.quote_id == context.target_quote_id),
            None,
        )
        competitor = next(
            (quote for quote in quotes if quote.quote_id == context.competitor_quote_id),
            None,
        )
        if target is None or not _eligible_quote(
            target,
            attempt.job_id,
            attempt.job_spec_version,
        ):
            raise DomainConflict("Negotiation target quote is no longer eligible")
        if (
            competitor is None
            or competitor.vendor.vendor_id == target.vendor.vendor_id
            or not _eligible_quote(
                competitor,
                attempt.job_id,
                attempt.job_spec_version,
            )
        ):
            raise DomainConflict("Negotiation competitor quote is no longer eligible")
        leverage_total = (
            competitor.comparable_total
            if competitor.comparable_total is not None
            else competitor.negotiated_total
        )
        if leverage_total != context.eligible_leverage_total:
            raise DomainConflict("Negotiation leverage no longer matches stored context")
        if not _eligible_quote(
            improved,
            attempt.job_id,
            attempt.job_spec_version,
        ):
            raise DomainConflict("Negotiation result is not a verified eligible quote")
        if not is_measurable_quote_improvement(target, improved):
            raise DomainConflict("Negotiation did not measurably improve price or terms")

    def _require_job(self, job_id: UUID) -> JobRecord:
        record = self._jobs.get(job_id)
        if record is None:
            raise ResourceNotFound(f"Job {job_id} was not found")
        return record


class _IntakeStore:
    """Adapt separate typed repositories to IntakeSessionService's combined store."""

    def __init__(
        self,
        sessions: IntakeSessionRepository,
        jobs: JobRepository,
    ) -> None:
        self._sessions = sessions
        self._jobs = jobs

    def create_intake_session(self, session: IntakeSession) -> IntakeSession:
        return self._sessions.create_intake_session(session)

    def get_intake_session(self, session_id: UUID) -> IntakeSession | None:
        return self._sessions.get_intake_session(session_id)

    def find_intake_session_by_conversation_id(
        self,
        conversation_id: str,
    ) -> IntakeSession | None:
        return self._sessions.find_intake_session_by_conversation_id(conversation_id)

    def save_intake_session(self, session: IntakeSession) -> IntakeSession:
        return self._sessions.save_intake_session(session)

    def reserve_intake_browser_credential(
        self,
        session_id: UUID,
        issued_at: datetime,
    ) -> IntakeSession:
        return self._sessions.reserve_intake_browser_credential(session_id, issued_at)

    def get(self, job_id: UUID) -> JobRecord | None:
        return self._jobs.get(job_id)

    def claim_intake_resume(
        self,
        session_id: UUID,
        child: IntakeSession,
        now: datetime,
    ) -> IntakeSession:
        return self._sessions.claim_intake_resume(session_id, child, now)

    def finish_intake_manually(
        self,
        session_id: UUID,
        job: JobRecord,
        now: datetime,
    ) -> JobRecord:
        return self._sessions.finish_intake_manually(session_id, job, now)


def _intake_job_spec(
    event: VerifiedPostCallTranscription,
    session: IntakeSession,
    *,
    require_summary: bool = True,
) -> JobSpecV1:
    data = event.collected_data
    if data.get("recording_consent") is not True:
        raise DomainConflict("Voice intake requires recording consent")
    if require_summary and data.get("summary_confirmed") is not True:
        raise DomainConflict("Voice intake requires confirmed summary readback")
    origin = OriginDestinationAccess(
        address_summary=_optional_string(data.get("origin_address_summary")),
        dwelling_type=_optional_dwelling(data.get("origin_dwelling_type")),
        floors=_optional_integer(data.get("origin_floors"), "origin_floors"),
        stairs=_optional_integer(data.get("origin_stairs"), "origin_stairs"),
        elevator_access=_optional_boolean(
            data.get("origin_elevator_access"),
            "origin_elevator_access",
        ),
        parking_distance_feet=_optional_integer(
            data.get("origin_parking_distance_feet"),
            "origin_parking_distance_feet",
        ),
    )
    destination = OriginDestinationAccess(
        address_summary=_optional_string(data.get("destination_address_summary")),
        dwelling_type=_optional_dwelling(data.get("destination_dwelling_type")),
        floors=_optional_integer(data.get("destination_floors"), "destination_floors"),
        stairs=_optional_integer(data.get("destination_stairs"), "destination_stairs"),
        elevator_access=_optional_boolean(
            data.get("destination_elevator_access"),
            "destination_elevator_access",
        ),
        parking_distance_feet=_optional_integer(
            data.get("destination_parking_distance_feet"),
            "destination_parking_distance_feet",
        ),
    )
    try:
        result = JobSpecV1(
            job_id=session.job_id,
            intake_source=IntakeSource.VOICE,
            move_date=_optional_date(data.get("move_date")),
            date_flexible=_optional_boolean(data.get("date_flexible"), "date_flexible"),
            origin=origin,
            destination=destination,
            bedroom_count=_optional_integer(data.get("bedroom_count"), "bedroom_count"),
            inventory=_inventory(data.get("inventory_json"), session.intake_session_id),
            oversized_or_fragile_items=_string_list(
                data.get("special_items_json"),
                "special_items_json",
            ),
            services=MovingServices(
                packing=_optional_boolean(data.get("packing"), "packing"),
                disassembly=_optional_boolean(data.get("disassembly"), "disassembly"),
                storage=_optional_boolean(data.get("storage"), "storage"),
                storage_days=_optional_integer(data.get("storage_days"), "storage_days"),
            ),
            insurance_preference=_optional_string(data.get("insurance_preference")),
            confirmed=False,
            confirmed_at=None,
            locked_version=None,
            data_classification=(
                DataClassification.REAL_REDACTED
                if session.data_mode is IntakeDataMode.REAL_REDACTED
                else DataClassification.ROLE_PLAY
            ),
        )
    except ValidationError as exc:
        raise DomainConflict("Voice intake fields do not form a valid JobSpecV1") from exc
    if session.data_mode is IntakeDataMode.REAL_REDACTED:
        for access in (result.origin, result.destination):
            if (
                access.address_summary is not None
                and _REDACTED_CITY_STATE.fullmatch(access.address_summary) is None
            ):
                raise DomainConflict(
                    "Real-redacted voice intake requires city and state only"
                )
    return result


def _completed_intake_materialization(
    session: IntakeSession,
    event: VerifiedPostCallTranscription,
    job_spec: JobSpecV1,
) -> VoiceIntakeCompletion:
    record = JobRecord(
        job_spec=job_spec,
        state=JobState.INTAKE_COMPLETE,
        created_at=event.event_timestamp,
        updated_at=event.event_timestamp,
    )
    completed_session = session.model_copy(
        update={
            "conversation_id": event.conversation_id,
            "status": IntakeSessionStatus.COMPLETED,
            "updated_at": event.event_timestamp,
            "completed_at": event.event_timestamp,
        },
        deep=True,
    )
    return VoiceIntakeCompletion(
        session=completed_session,
        job=record,
        event=JobEvent(
            event_id=uuid5(
                NAMESPACE_URL,
                f"voice-intake-event:{event.event_type}:{session.intake_session_id}",
            ),
            job_id=record.job_spec.job_id,
            event_type=event.event_type,
            occurred_at=event.event_timestamp,
            metadata={"provider_status": event.provider_status},
        ),
    )


def _failed_intake_materialization(
    session: IntakeSession,
    event: VerifiedPostCallTranscription,
    failure_code: str,
) -> VoiceIntakeFailure:
    return VoiceIntakeFailure(
        session=session.model_copy(
            update={
                "conversation_id": event.conversation_id,
                "status": IntakeSessionStatus.FAILED,
                "failure_code": failure_code,
                "updated_at": event.event_timestamp,
            },
            deep=True,
        ),
        event_type=event.event_type,
    )


def _has_collected_move_fact(data: dict[str, Any]) -> bool:
    return any(
        key not in _INTAKE_CONTROL_FIELDS and value is not None
        for key, value in data.items()
    )


def _merge_intake_specs(
    base: JobSpecV1 | None,
    collected: JobSpecV1,
    collected_data: dict[str, Any],
) -> JobSpecV1:
    if base is None:
        return collected

    def choose(key: str, previous: Any, replacement: Any) -> Any:
        if key in collected_data and collected_data[key] is not None:
            return replacement
        return previous

    def merge_access(
        previous: OriginDestinationAccess,
        replacement: OriginDestinationAccess,
        prefix: str,
    ) -> OriginDestinationAccess:
        return OriginDestinationAccess(
            address_summary=choose(
                f"{prefix}_address_summary",
                previous.address_summary,
                replacement.address_summary,
            ),
            dwelling_type=choose(
                f"{prefix}_dwelling_type",
                previous.dwelling_type,
                replacement.dwelling_type,
            ),
            floors=choose(f"{prefix}_floors", previous.floors, replacement.floors),
            stairs=choose(f"{prefix}_stairs", previous.stairs, replacement.stairs),
            elevator_access=choose(
                f"{prefix}_elevator_access",
                previous.elevator_access,
                replacement.elevator_access,
            ),
            parking_distance_feet=choose(
                f"{prefix}_parking_distance_feet",
                previous.parking_distance_feet,
                replacement.parking_distance_feet,
            ),
            access_notes=previous.access_notes,
        )

    storage = choose("storage", base.services.storage, collected.services.storage)
    storage_days = choose(
        "storage_days",
        base.services.storage_days,
        collected.services.storage_days,
    )
    if storage is not True:
        storage_days = None
    merged = base.model_copy(
        update={
            "job_id": collected.job_id,
            "intake_source": IntakeSource.VOICE,
            "move_date": choose("move_date", base.move_date, collected.move_date),
            "date_flexible": choose(
                "date_flexible",
                base.date_flexible,
                collected.date_flexible,
            ),
            "origin": merge_access(base.origin, collected.origin, "origin"),
            "destination": merge_access(
                base.destination,
                collected.destination,
                "destination",
            ),
            "bedroom_count": choose(
                "bedroom_count",
                base.bedroom_count,
                collected.bedroom_count,
            ),
            "inventory": choose(
                "inventory_json",
                base.inventory,
                collected.inventory,
            ),
            "oversized_or_fragile_items": choose(
                "special_items_json",
                base.oversized_or_fragile_items,
                collected.oversized_or_fragile_items,
            ),
            "services": MovingServices(
                packing=choose(
                    "packing",
                    base.services.packing,
                    collected.services.packing,
                ),
                disassembly=choose(
                    "disassembly",
                    base.services.disassembly,
                    collected.services.disassembly,
                ),
                storage=storage,
                storage_days=storage_days,
            ),
            "insurance_preference": choose(
                "insurance_preference",
                base.insurance_preference,
                collected.insurance_preference,
            ),
            "confirmed": False,
            "confirmed_at": None,
            "locked_version": None,
            "data_classification": collected.data_classification,
        },
        deep=True,
    )
    try:
        return JobSpecV1.model_validate(merged.model_dump(mode="json"))
    except ValidationError as exc:
        raise DomainConflict("Resumed voice intake does not form a valid JobSpecV1") from exc


def _inventory(value: Any, session_id: UUID) -> list[InventoryItem]:
    raw = _json_list(value, "inventory_json")
    items: list[InventoryItem] = []
    try:
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                raise DomainConflict("inventory_json contains an invalid item")
            payload = dict(item)
            legacy_name = payload.pop("item", None)
            if "name" not in payload and isinstance(legacy_name, str):
                payload["name"] = legacy_name
            elif legacy_name is not None and legacy_name != payload.get("name"):
                raise DomainConflict("inventory_json contains an invalid item")
            if payload.get("room") is None:
                payload["room"] = "Unspecified"
            payload["item_id"] = uuid5(
                NAMESPACE_URL,
                f"voice-intake:{session_id}:inventory:{index}",
            )
            items.append(InventoryItem.model_validate(payload))
    except ValidationError as exc:
        raise DomainConflict("inventory_json contains an invalid item") from exc
    return items


def _string_list(value: Any, field_name: str) -> list[str]:
    raw = _json_list(value, field_name)
    if any(
        not isinstance(item, str) or not item.strip() or len(item.strip()) > MAX_SPECIAL_ITEM_LENGTH
        for item in raw
    ):
        raise DomainConflict(f"{field_name} contains an invalid item")
    return list(dict.fromkeys(item.strip() for item in raw))


def _json_list(value: Any, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, str):
        raise DomainConflict(f"{field_name} must be JSON text")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise DomainConflict(f"{field_name} must be valid JSON") from exc
    if not isinstance(parsed, list):
        raise DomainConflict(f"{field_name} must contain a JSON list")
    if len(parsed) > MAX_INTAKE_LIST_ITEMS:
        raise DomainConflict(f"{field_name} contains too many items")
    return parsed


def _optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainConflict("move_date must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise DomainConflict("move_date must be an ISO date") from None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DomainConflict("Voice intake text value is invalid")
    return value.strip()


def _optional_boolean(value: Any, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise DomainConflict(f"{field_name} must be boolean")
    return value


def _optional_integer(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise DomainConflict(f"{field_name} must be an integer")
    return value


def _optional_dwelling(value: Any) -> DwellingType | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DomainConflict("Voice intake dwelling type is invalid")
    normalized = " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())
    if normalized == "other":
        return DwellingType.OTHER
    patterns = {
        DwellingType.APARTMENT: (r"\bapartment\b", r"\bapt\b"),
        DwellingType.CONDO: (r"\bcondo\b", r"\bcondominium\b"),
        DwellingType.TOWNHOUSE: (r"\btownhouse\b", r"\btownhome\b"),
        DwellingType.HOUSE: (r"\bhouse\b", r"\bsingle family\b"),
        DwellingType.STORAGE_UNIT: (r"\bstorage unit\b",),
    }
    matches = {
        dwelling
        for dwelling, dwelling_patterns in patterns.items()
        if any(re.search(pattern, normalized) for pattern in dwelling_patterns)
    }
    if len(matches) == 1:
        return matches.pop()
    try:
        return DwellingType(value)
    except (TypeError, ValueError):
        raise DomainConflict("Voice intake dwelling type is invalid") from None


def _eligible_quote(
    quote: QuoteV1,
    job_id: UUID,
    job_spec_version: str,
) -> bool:
    return (
        is_quote_eligible(
            quote,
            job_id=job_id,
            job_spec_version=job_spec_version,
        )
        and (quote.comparable_total is not None or quote.negotiated_total is not None)
    )


__all__ = ["VoiceMaterializer"]
