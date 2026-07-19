"""End-to-end orchestration tests for signed asynchronous voice results."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from services.api.app.contracts import (
    CallOutcomeType,
    CallStatus,
    DataClassification,
    FeeCategory,
    IntakeSource,
    JobState,
    VerificationStatus,
)
from services.api.app.core.errors import DomainConflict
from services.api.app.integrations.elevenlabs.webhook import ElevenLabsWebhookProcessor
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.orchestration.intake_sessions import (
    IntakeSessionService,
    IntakeSessionStatus,
)
from services.api.app.orchestration.mock_intelligence import MockIntelligenceProvider
from services.api.app.orchestration.models import VoiceCallReference, VoiceCallResult
from services.api.app.orchestration.recording_capability import RecordingCapabilitySigner
from services.api.app.orchestration.role_play import FixtureRolePlayVendorRoster
from services.api.app.orchestration.service import VeraMoveService
from services.api.app.repositories.memory import InMemoryRepository

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
SECRET = "synthetic-async-webhook-secret"
INTAKE_AGENT_ID = "agent_synthetic_intake"
OUTBOUND_AGENT_ID = "agent_synthetic_outbound"
CONFIG_VERSION = "2026-07-19.1"


class AcceptedAsyncVoiceProvider:
    """Accept calls but leave all canonical results to signed webhooks."""

    initial_call_limit = 3
    outbound_agent_id = OUTBOUND_AGENT_ID
    agent_config_version = CONFIG_VERSION

    def initiate_quote_call(self, job_spec, vendor, call_id, destination_slot):
        del job_spec, vendor
        return VoiceCallResult(
            reference=VoiceCallReference(
                conversation_id=f"conv_synthetic_quote_{destination_slot}_{call_id}",
                provider_call_id=f"CA_synthetic_quote_{destination_slot}_{call_id}",
            )
        )

    def initiate_negotiation_call(
        self,
        job_spec,
        target_vendor,
        verified_competitor,
        planned_quote,
        call_id,
        destination_slot,
    ):
        del job_spec, target_vendor, verified_competitor, planned_quote
        return VoiceCallResult(
            reference=VoiceCallReference(
                conversation_id=f"conv_synthetic_negotiation_{destination_slot}_{call_id}",
                provider_call_id=f"CA_synthetic_negotiation_{destination_slot}_{call_id}",
            )
        )


def _service(fixtures, *, with_recording_signer: bool = True):
    repository = InMemoryRepository()
    service = VeraMoveService(
        jobs=repository,
        calls=repository,
        quotes=repository,
        intake_sessions=repository,
        voice=AcceptedAsyncVoiceProvider(),
        intelligence=MockIntelligenceProvider(
            fixtures,
            MockNegotiationGateway(fixtures),
        ),
        discovery=MockVendorDiscoveryGateway(fixtures),
        webhooks=ElevenLabsWebhookProcessor(secret=SECRET, clock=lambda: NOW),
        fixtures=fixtures,
        vendor_roster=FixtureRolePlayVendorRoster(fixtures),
        recording_signer=(
            RecordingCapabilitySigner(
                "https://api.synthetic-veramove.example",
                "r" * 32,
            )
            if with_recording_signer
            else None
        ),
        required_fee_categories={FeeCategory.BASE_SERVICE, FeeCategory.STAIRS},
        clock=lambda: NOW,
    )
    return service, repository


def _sign(body: bytes, timestamp: datetime = NOW) -> str:
    unix_time = int(timestamp.timestamp())
    digest = hmac.new(
        SECRET.encode(),
        str(unix_time).encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return f"t={unix_time},v0={digest}"


def _provider_body(
    *,
    agent_id: str,
    conversation_id: str,
    dynamic_variables: dict,
    collected_data: dict,
    transcript: list[dict] | None = None,
    has_audio: bool = True,
) -> bytes:
    analysis = {
        "data_collection_results": {
            key: {"data_collection_id": key, "value": value}
            for key, value in collected_data.items()
        },
        "summary": "This arbitrary provider summary must never be persisted.",
    }
    return json.dumps(
        {
            "type": "post_call_transcription",
            "event_timestamp": (NOW + timedelta(seconds=30)).isoformat(),
            "data": {
                "agent_id": agent_id,
                "conversation_id": conversation_id,
                "status": "done",
                "version_id": "agtvrsn_synthetic_reviewed",
                "has_audio": has_audio,
                "conversation_initiation_client_data": {
                    "dynamic_variables": dynamic_variables,
                },
                "analysis": analysis,
                "transcript": transcript or [],
                "phone_number": "+15550101001",
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _outbound_body(
    attempt,
    *,
    total: int = 120,
    original_total: int | None = None,
) -> bytes:
    assert attempt.reference is not None
    starting_total = total if original_total is None else original_total
    return _provider_body(
        agent_id=OUTBOUND_AGENT_ID,
        conversation_id=attempt.reference.conversation_id,
        dynamic_variables={
            "job_id": str(attempt.job_id),
            "call_id": str(attempt.call_id),
            "vendor_id": str(attempt.vendor.vendor_id),
            "call_mode": attempt.call_mode,
            "job_spec_version": attempt.job_spec_version,
            "agent_config_version": attempt.agent_config_version,
            "job_spec_sha256": attempt.job_spec_sha256,
        },
        collected_data={
            "recording_consent": True,
            "outcome_type": "itemized_quote",
            "headline_total": total,
            "original_total": starting_total,
            "negotiated_total": total,
            "deposit": 12,
            "binding_type": "binding",
            "availability_status": "available",
            "availability": "Available on the synthetic requested date.",
            "fee_items_json": json.dumps(
                [
                    {
                        "category": "base_service",
                        "description": "Synthetic base service fee.",
                        "amount": f"{total - 20}.00",
                        "mandatory": True,
                    },
                    {
                        "category": "stairs",
                        "description": "Synthetic stairs fee.",
                        "amount": "20.00",
                        "mandatory": True,
                    },
                ]
            ),
            "addressed_fee_categories_json": json.dumps(["base_service", "stairs"]),
            "concessions_json": "[]",
        },
        transcript=[
            {
                "role": "user",
                "message": f"The base service fee is ${total - 20}.00.",
                "time_in_call_secs": 5,
            },
            {
                "role": "user",
                "message": "The stairs fee is $20.00.",
                "time_in_call_secs": 10,
            },
            {
                "role": "user",
                "message": f"The all-in total is ${total}.00.",
                "time_in_call_secs": 15,
            },
            {
                "role": "user",
                "message": "This is a binding quote and we are available.",
                "time_in_call_secs": 20,
            },
            {
                "role": "agent",
                "message": "Unrelated transcript chatter must remain transient.",
                "time_in_call_secs": 25,
            },
        ],
    )


def _intake_collected_data() -> dict:
    return {
        "recording_consent": True,
        "summary_confirmed": True,
        "move_date": "2026-08-01",
        "date_flexible": True,
        "origin_address_summary": "Synthetic origin in Boston, MA",
        "origin_dwelling_type": "apartment",
        "origin_floors": 2,
        "origin_stairs": 12,
        "origin_elevator_access": False,
        "origin_parking_distance_feet": 50,
        "destination_address_summary": "Synthetic destination in Cambridge, MA",
        "destination_dwelling_type": "condo",
        "destination_floors": 4,
        "destination_stairs": 0,
        "destination_elevator_access": True,
        "destination_parking_distance_feet": 25,
        "bedroom_count": 1,
        "inventory_json": json.dumps(
            [{"name": "Synthetic sofa", "quantity": 1, "room": "Living room"}]
        ),
        "special_items_json": json.dumps(["Synthetic fragile lamp"]),
        "packing": False,
        "disassembly": True,
        "storage": False,
        "storage_days": None,
        "insurance_preference": "Synthetic standard coverage",
    }


def test_signed_outbound_completion_materializes_one_canonical_quote(fixtures, job_spec):
    service, repository = _service(fixtures)
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)
    calling = service.start_calls(job_spec.job_id)
    assert calling.state is JobState.CALLING
    attempt = service.list_call_attempts(job_spec.job_id)[0]
    body = _outbound_body(attempt)

    first = service.handle_elevenlabs_webhook(body, _sign(body))
    second = service.handle_elevenlabs_webhook(body, _sign(body))

    assert first.accepted is True and first.duplicate is False
    assert second.accepted is False and second.duplicate is True
    stored = service.get_job(job_spec.job_id)
    assert len(stored.calls) == 1
    assert len(stored.quotes) == 1
    assert stored.calls[0].outcome.type is CallOutcomeType.ITEMIZED_QUOTE
    assert stored.calls[0].recording_url == stored.quotes[0].recording_url
    assert stored.calls[0].status is CallStatus.COMPLETED
    assert repository.get_attempt(attempt.call_id).provider_version_id == (
        "agtvrsn_synthetic_reviewed"
    )
    persisted = repr(repository._jobs) + repr(repository._events)
    assert "arbitrary provider summary" not in persisted
    assert "+15550101001" not in persisted
    assert "Unrelated transcript chatter" not in persisted


def test_outbound_mismatch_is_failed_once_without_canonical_write(fixtures, job_spec):
    service, _ = _service(fixtures)
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)
    service.start_calls(job_spec.job_id)
    attempt = service.list_call_attempts(job_spec.job_id)[0]
    body = _outbound_body(attempt)
    payload = json.loads(body)
    payload["data"]["conversation_initiation_client_data"]["dynamic_variables"][
        "agent_config_version"
    ] = "wrong-version"
    mismatched = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()

    with pytest.raises(DomainConflict, match="agent_config"):
        service.handle_elevenlabs_webhook(mismatched, _sign(mismatched))

    replay = service.handle_elevenlabs_webhook(body, _sign(body))
    assert replay.accepted is False and replay.duplicate is True
    assert service.get_job(job_spec.job_id).calls == []


def test_itemized_quote_fails_closed_without_recording_capability(fixtures, job_spec):
    service, _ = _service(fixtures, with_recording_signer=False)
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)
    service.start_calls(job_spec.job_id)
    attempt = service.list_call_attempts(job_spec.job_id)[0]
    body = _outbound_body(attempt)

    with pytest.raises(DomainConflict, match="recording capability"):
        service.handle_elevenlabs_webhook(body, _sign(body))

    assert service.get_job(job_spec.job_id).calls == []


def test_signed_intake_completion_creates_one_unconfirmed_voice_job(fixtures):
    service, repository = _service(fixtures)
    sessions = IntakeSessionService(
        repository,
        expected_agent_id=INTAKE_AGENT_ID,
        agent_config_version=CONFIG_VERSION,
        clock=lambda: NOW,
    )
    session_view = sessions.create_web_session()
    conversation_id = "conv_synthetic_intake_1"
    sessions.attach_conversation(
        session_view.intake_session_id,
        conversation_id,
        agent_id=INTAKE_AGENT_ID,
    )
    body = _provider_body(
        agent_id=INTAKE_AGENT_ID,
        conversation_id=conversation_id,
        dynamic_variables={
            "job_id": str(session_view.job_id),
            "intake_session_id": str(session_view.intake_session_id),
            "agent_config_version": CONFIG_VERSION,
        },
        collected_data=_intake_collected_data(),
        transcript=[
            {
                "role": "user",
                "message": "Synthetic caller transcript must be transient.",
                "time_in_call_secs": 5,
            }
        ],
    )

    first = service.handle_elevenlabs_webhook(body, _sign(body))
    second = service.handle_elevenlabs_webhook(body, _sign(body))

    assert first.accepted is True and first.duplicate is False
    assert second.accepted is False and second.duplicate is True
    record = service.get_job(session_view.job_id)
    assert record.state is JobState.INTAKE_COMPLETE
    assert record.job_spec.intake_source is IntakeSource.VOICE
    assert record.job_spec.data_classification is DataClassification.ROLE_PLAY
    assert record.job_spec.confirmed is False
    assert record.job_spec.confirmed_at is None
    assert record.job_spec.locked_version is None
    assert record.job_spec.missing_required_fields() == []
    assert len(record.job_spec.inventory) == 1
    session = repository.get_intake_session(session_view.intake_session_id)
    assert session is not None and session.status is IntakeSessionStatus.COMPLETED
    assert repository._webhook_keys == set()
    assert len(repository._voice_webhook_receipts) == 1
    assert next(iter(repository._voice_webhook_receipts.values()))["status"] == "processed"
    persisted = repr(repository._jobs) + repr(repository._intake_sessions)
    assert "Synthetic caller transcript" not in persisted
    assert "+15550101001" not in persisted


def test_intake_finalizer_failure_leaves_no_partial_job_and_can_retry(
    fixtures,
    monkeypatch,
):
    service, repository = _service(fixtures)
    sessions = IntakeSessionService(
        repository,
        expected_agent_id=INTAKE_AGENT_ID,
        agent_config_version=CONFIG_VERSION,
        clock=lambda: NOW,
    )
    session_view = sessions.create_web_session()
    conversation_id = "conv_synthetic_retryable_intake"
    sessions.attach_conversation(
        session_view.intake_session_id,
        conversation_id,
        agent_id=INTAKE_AGENT_ID,
    )
    body = _provider_body(
        agent_id=INTAKE_AGENT_ID,
        conversation_id=conversation_id,
        dynamic_variables={
            "job_id": str(session_view.job_id),
            "intake_session_id": str(session_view.intake_session_id),
            "agent_config_version": CONFIG_VERSION,
        },
        collected_data=_intake_collected_data(),
    )
    original_finalize = repository.finalize_voice_intake_webhook

    def fail_finalize(*_args, **_kwargs):
        raise RuntimeError("synthetic transient persistence failure")

    monkeypatch.setattr(repository, "finalize_voice_intake_webhook", fail_finalize)
    with pytest.raises(RuntimeError, match="transient persistence"):
        service.handle_elevenlabs_webhook(body, _sign(body))

    assert repository.get(session_view.job_id) is None
    unchanged = repository.get_intake_session(session_view.intake_session_id)
    assert unchanged is not None and unchanged.status is IntakeSessionStatus.IN_PROGRESS
    receipt = next(iter(repository._voice_webhook_receipts.values()))
    assert receipt["status"] == "failed" and receipt["retryable"] is True

    monkeypatch.setattr(
        repository,
        "finalize_voice_intake_webhook",
        original_finalize,
    )
    retried = service.handle_elevenlabs_webhook(body, _sign(body))
    assert retried.accepted is True and retried.duplicate is False
    assert service.get_job(session_view.job_id).state is JobState.INTAKE_COMPLETE


def test_signed_intake_initiation_failure_is_atomic_and_duplicate_safe(fixtures):
    service, repository = _service(fixtures)
    sessions = IntakeSessionService(
        repository,
        expected_agent_id=INTAKE_AGENT_ID,
        agent_config_version=CONFIG_VERSION,
        clock=lambda: NOW,
    )
    session_view = sessions.create_web_session()
    conversation_id = "conv_synthetic_failed_intake"
    sessions.attach_conversation(
        session_view.intake_session_id,
        conversation_id,
        agent_id=INTAKE_AGENT_ID,
    )
    body = json.dumps(
        {
            "type": "call_initiation_failure",
            "event_timestamp": (NOW + timedelta(seconds=30)).isoformat(),
            "data": {
                "agent_id": INTAKE_AGENT_ID,
                "conversation_id": conversation_id,
                "failure_reason": "no-answer",
                "phone_number": "+15550101003",
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

    first = service.handle_elevenlabs_webhook(body, _sign(body))
    second = service.handle_elevenlabs_webhook(body, _sign(body))

    assert first.accepted is True and first.duplicate is False
    assert second.accepted is False and second.duplicate is True
    stored = repository.get_intake_session(session_view.intake_session_id)
    assert stored is not None
    assert stored.status is IntakeSessionStatus.FAILED
    assert stored.failure_code == "provider_no_answer"
    assert repository.get(session_view.job_id) is None
    assert repository._webhook_keys == set()
    assert len(repository._voice_webhook_receipts) == 1
    assert next(iter(repository._voice_webhook_receipts.values()))["status"] == "processed"
    persisted = repr(repository._intake_sessions) + repr(
        repository._voice_webhook_receipts
    )
    assert "+15550101003" not in persisted


def test_signed_initiation_failure_becomes_one_failed_call(fixtures, job_spec):
    service, _ = _service(fixtures)
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)
    service.start_calls(job_spec.job_id)
    attempt = service.list_call_attempts(job_spec.job_id)[0]
    assert attempt.reference is not None
    body = json.dumps(
        {
            "type": "call_initiation_failure",
            "event_timestamp": (NOW + timedelta(seconds=30)).isoformat(),
            "data": {
                "agent_id": OUTBOUND_AGENT_ID,
                "conversation_id": attempt.reference.conversation_id,
                "failure_reason": "no-answer",
                "phone_number": "+15550101002",
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

    first = service.handle_elevenlabs_webhook(body, _sign(body))
    second = service.handle_elevenlabs_webhook(body, _sign(body))

    assert first.accepted is True and first.duplicate is False
    assert second.accepted is False and second.duplicate is True
    record = service.get_job(job_spec.job_id)
    assert len(record.calls) == 1
    assert record.calls[0].status is CallStatus.FAILED
    assert record.calls[0].outcome.type is CallOutcomeType.FAILED
    assert record.calls[0].recording_url is None
    assert "+15550101002" not in repr(record)

    remaining = service.list_call_attempts(job_spec.job_id)[1:]
    for remaining_attempt in remaining:
        completion = _outbound_body(remaining_attempt)
        service.handle_elevenlabs_webhook(completion, _sign(completion))

    completed_batch = service.get_job(job_spec.job_id)
    assert completed_batch.state is JobState.QUOTES_READY
    assert len(completed_batch.calls) == 3
    assert len(completed_batch.quotes) == 2


def test_three_signed_quotes_and_one_improved_negotiation_complete_workflow(
    fixtures,
    job_spec,
):
    service, repository = _service(fixtures)
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)
    service.start_calls(job_spec.job_id)

    initial_attempts = service.list_call_attempts(job_spec.job_id)
    assert len(initial_attempts) == 3
    for attempt, total in zip(initial_attempts, (120, 140, 160), strict=True):
        body = _outbound_body(attempt, total=total)
        acknowledgement = service.handle_elevenlabs_webhook(body, _sign(body))
        assert acknowledgement.accepted is True

    quotes_ready = service.get_job(job_spec.job_id)
    assert quotes_ready.state is JobState.QUOTES_READY
    assert len(quotes_ready.calls) == 3
    assert len(quotes_ready.quotes) == 3

    negotiating = service.initiate_negotiation_call(job_spec.job_id)
    assert negotiating.state is JobState.NEGOTIATING
    negotiation_attempt = service.list_call_attempts(job_spec.job_id)[-1]
    assert negotiation_attempt.call_mode == "negotiation"
    assert negotiation_attempt.negotiation_context is not None

    improved = _outbound_body(
        negotiation_attempt,
        total=115,
        original_total=160,
    )
    acknowledgement = service.handle_elevenlabs_webhook(improved, _sign(improved))

    assert acknowledgement.accepted is True
    completed = service.get_job(job_spec.job_id)
    assert completed.state is JobState.COMPLETED
    assert len(completed.calls) == 4
    assert len(completed.quotes) == 4
    assert completed.recommendation is not None
    assert completed.recommendation.winning_vendor_id == negotiation_attempt.vendor.vendor_id
    assert completed.recommendation.rankings[0].quote_id == completed.quotes[-1].quote_id
    assert completed.recommendation.rankings[0].total == Decimal("115.00")
    assert all(call.recording_url is not None for call in completed.calls)
    assert repository.get_job_revision(job_spec.job_id) == 4


def test_recommendation_excludes_ineligible_quote_even_when_it_is_cheapest(
    fixtures,
    job_spec,
):
    service, _ = _service(fixtures)
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)
    service.start_calls(job_spec.job_id)
    for attempt in service.list_call_attempts(job_spec.job_id):
        body = _outbound_body(attempt)
        service.handle_elevenlabs_webhook(body, _sign(body))

    record = service.get_job(job_spec.job_id)
    ineligible = record.quotes[0].model_copy(
        update={
            "quote_id": uuid4(),
            "headline_total": Decimal("1.00"),
            "original_total": Decimal("1.00"),
            "negotiated_total": Decimal("1.00"),
            "comparable_total": Decimal("1.00"),
            "verification_status": VerificationStatus.PROVISIONAL,
            "verified_data": {},
            "transcript_evidence": [],
            "recording_url": None,
        },
        deep=True,
    )
    record.quotes.append(ineligible)

    recommendation = service._build_recommendation(record)

    assert all(item.quote_id != ineligible.quote_id for item in recommendation.rankings)
    assert ineligible.quote_id not in {
        quote.quote_id
        for quote in record.quotes
        if quote.verification_status is VerificationStatus.VERIFIED
    }
