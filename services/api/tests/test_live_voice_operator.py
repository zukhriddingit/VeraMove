"""Service-boundary tests for signed recording playback and operator repair."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from services.api.app.contracts import (
    CallOutcome,
    CallOutcomeType,
    CallRecord,
    CallStatus,
)
from services.api.app.core.errors import (
    DomainConflict,
    ProviderConfigurationError,
    ProviderRequestError,
    ResourceNotFound,
    WebhookAuthenticationError,
)
from services.api.app.integrations.elevenlabs.conversations import (
    ConversationRepairSnapshot,
)
from services.api.app.integrations.elevenlabs.models import (
    ElevenLabsDynamicVariables,
    VerifiedPostCallTranscription,
)
from services.api.app.integrations.elevenlabs.recordings import (
    MAX_RECORDING_BYTES,
    RecordingAudio,
)
from services.api.app.orchestration import live_voice_operator
from services.api.app.orchestration.live_voice_operator import (
    CompletedConversationRepairInput,
    FailedConversationRepairInput,
    LiveVoiceOperatorService,
)
from services.api.app.orchestration.models import (
    CallAttempt,
    CallKind,
    VoiceCallReference,
)
from services.api.app.orchestration.recording_capability import (
    RecordingCapabilitySigner,
)

FIXED_NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
OPERATOR_SECRET = "o" * 32


class StaticCallLookup:
    def __init__(
        self,
        *,
        calls: list[CallRecord] | None = None,
        attempts: list[CallAttempt] | None = None,
    ) -> None:
        self.calls = calls or []
        self.attempts = {
            attempt.call_id: attempt for attempt in attempts or []
        }
        self.list_requests: list[UUID] = []
        self.attempt_requests: list[UUID] = []

    def list_calls(self, job_id: UUID) -> list[CallRecord]:
        self.list_requests.append(job_id)
        return [call for call in self.calls if call.job_id == job_id]

    def get_attempt(self, call_id: UUID) -> CallAttempt | None:
        self.attempt_requests.append(call_id)
        return self.attempts.get(call_id)


class StaticConversationClient:
    def __init__(self, snapshot: ConversationRepairSnapshot) -> None:
        self.snapshot = snapshot
        self.requests: list[str] = []

    def fetch_for_repair(self, conversation_id: str) -> ConversationRepairSnapshot:
        self.requests.append(conversation_id)
        return self.snapshot


class StaticRecordingClient:
    def __init__(self, audio: RecordingAudio) -> None:
        self.audio = audio
        self.requests: list[tuple[str, bool]] = []

    def fetch_audio(self, conversation_id: str, *, has_audio: bool) -> RecordingAudio:
        self.requests.append((conversation_id, has_audio))
        return self.audio


def make_attempt(job_spec, vendor) -> CallAttempt:
    return CallAttempt(
        call_id=uuid4(),
        job_id=job_spec.job_id,
        kind=CallKind.QUOTE,
        vendor=vendor,
        job_spec_snapshot=job_spec,
        destination_slot=0,
        expected_agent_id="synthetic-outbound-agent",
        agent_config_version="2026-07-19.1",
        status=CallStatus.IN_PROGRESS,
        started_at=FIXED_NOW,
        reference=VoiceCallReference(
            conversation_id="conv_synthetic_operator",
            provider_call_id="CA_synthetic_operator",
        ),
    )


def make_call(attempt: CallAttempt, recording_url) -> CallRecord:
    return CallRecord(
        call_id=attempt.call_id,
        job_id=attempt.job_id,
        vendor=attempt.vendor,
        status=CallStatus.COMPLETED,
        started_at=attempt.started_at,
        completed_at=FIXED_NOW.replace(minute=5),
        outcome=CallOutcome(
            type=CallOutcomeType.DOCUMENTED_DECLINE,
            reason="Synthetic role-play participant declined.",
        ),
        recording_url=recording_url,
    )


def make_completed_event(attempt: CallAttempt) -> VerifiedPostCallTranscription:
    assert attempt.reference is not None
    return VerifiedPostCallTranscription(
        idempotency_key="repair-synthetic-event",
        event_timestamp=FIXED_NOW,
        agent_id=attempt.expected_agent_id,
        conversation_id=attempt.reference.conversation_id,
        provider_status="done",
        call_status=CallStatus.COMPLETED,
        has_audio=True,
        dynamic_variables=ElevenLabsDynamicVariables(
            job_id=attempt.job_id,
            call_id=attempt.call_id,
            vendor_id=attempt.vendor.vendor_id,
            call_mode=attempt.call_mode,
            job_spec_version=attempt.job_spec_version,
            agent_config_version=attempt.agent_config_version,
            job_spec_sha256=attempt.job_spec_sha256,
        ),
        collected_data={
            "outcome_type": "failed",
            "outcome_reason": "Synthetic provider completion requires repair.",
            "recording_consent": False,
        },
    )


def make_operator_service(
    *,
    attempt: CallAttempt,
    signer: RecordingCapabilitySigner,
    snapshot: ConversationRepairSnapshot,
    call: CallRecord | None = None,
    audio: RecordingAudio | None = None,
):
    lookup = StaticCallLookup(
        calls=[call] if call is not None else [],
        attempts=[attempt],
    )
    conversations = StaticConversationClient(snapshot)
    recordings = StaticRecordingClient(
        audio or RecordingAudio(content=b"synthetic-audio", media_type="audio/mpeg")
    )
    service = LiveVoiceOperatorService(
        calls=lookup,
        signer=signer,
        conversations=conversations,
        recordings=recordings,
        operator_secret=OPERATOR_SECRET,
    )
    return service, lookup, conversations, recordings


def test_signed_recording_fetch_resolves_canonical_call_and_returns_no_store_payload(
    job_spec,
    fixtures,
):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    signer = RecordingCapabilitySigner("https://api.veramove.example", "r" * 32)
    recording_url = signer.build_url(attempt.call_id, attempt.job_id)
    call = make_call(attempt, recording_url)
    snapshot = ConversationRepairSnapshot(
        conversation_id=attempt.reference.conversation_id,
        agent_id=attempt.expected_agent_id,
        status="done",
        has_audio=True,
    )
    service, lookup, conversations, recordings = make_operator_service(
        attempt=attempt,
        signer=signer,
        snapshot=snapshot,
        call=call,
    )
    signature = str(recording_url).split("signature=", 1)[1]

    result = service.fetch_recording(
        call_id=attempt.call_id,
        job_id=attempt.job_id,
        signature=signature,
    )

    assert result.content == b"synthetic-audio"
    assert result.media_type == "audio/mpeg"
    assert result.content_length == len(result.content)
    assert result.cache_control == "no-store"
    assert lookup.list_requests == [attempt.job_id]
    assert lookup.attempt_requests == [attempt.call_id]
    assert conversations.requests == [attempt.reference.conversation_id]
    assert recordings.requests == [(attempt.reference.conversation_id, True)]


def test_recording_capability_tampering_fails_before_lookup_or_provider(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    signer = RecordingCapabilitySigner("https://api.veramove.example", "r" * 32)
    snapshot = ConversationRepairSnapshot(
        conversation_id=attempt.reference.conversation_id,
        agent_id=attempt.expected_agent_id,
        status="done",
        has_audio=True,
    )
    service, lookup, conversations, recordings = make_operator_service(
        attempt=attempt,
        signer=signer,
        snapshot=snapshot,
    )

    with pytest.raises(WebhookAuthenticationError, match="recording capability"):
        service.fetch_recording(
            call_id=attempt.call_id,
            job_id=uuid4(),
            signature="0" * 64,
        )

    assert lookup.list_requests == []
    assert lookup.attempt_requests == []
    assert conversations.requests == []
    assert recordings.requests == []


@pytest.mark.parametrize("status", ("initiated", "in-progress", "processing", "failed"))
def test_recording_fetch_rejects_non_done_conversations(job_spec, fixtures, status):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    signer = RecordingCapabilitySigner("https://api.veramove.example", "r" * 32)
    recording_url = signer.build_url(attempt.call_id, attempt.job_id)
    snapshot = ConversationRepairSnapshot(
        conversation_id=attempt.reference.conversation_id,
        agent_id=attempt.expected_agent_id,
        status=status,
        has_audio=True,
    )
    service, _, _, recordings = make_operator_service(
        attempt=attempt,
        signer=signer,
        snapshot=snapshot,
        call=make_call(attempt, recording_url),
    )

    with pytest.raises(DomainConflict, match="not ready"):
        service.fetch_recording(
            call_id=attempt.call_id,
            job_id=attempt.job_id,
            signature=str(recording_url).split("signature=", 1)[1],
        )

    assert recordings.requests == []


def test_recording_fetch_rejects_missing_call_attempt_audio_and_bad_audio(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    signer = RecordingCapabilitySigner("https://api.veramove.example", "r" * 32)
    recording_url = signer.build_url(attempt.call_id, attempt.job_id)
    snapshot = ConversationRepairSnapshot(
        conversation_id=attempt.reference.conversation_id,
        agent_id=attempt.expected_agent_id,
        status="done",
        has_audio=False,
    )
    service, _, _, recordings = make_operator_service(
        attempt=attempt,
        signer=signer,
        snapshot=snapshot,
        call=make_call(attempt, recording_url),
    )
    request = {
        "call_id": attempt.call_id,
        "job_id": attempt.job_id,
        "signature": str(recording_url).split("signature=", 1)[1],
    }

    with pytest.raises(ResourceNotFound, match="saved recording"):
        service.fetch_recording(**request)
    assert recordings.requests == []

    for audio, message in (
        (
            RecordingAudio.model_construct(content=b"synthetic", media_type="text/html"),
            "unsupported",
        ),
        (
            SimpleNamespace(
                content=b"x" * (MAX_RECORDING_BYTES + 1),
                media_type="audio/mpeg",
            ),
            "size limit",
        ),
    ):
        ready = snapshot.model_copy(update={"has_audio": True})
        unsafe_service, _, _, _ = make_operator_service(
            attempt=attempt,
            signer=signer,
            snapshot=ready,
            call=make_call(attempt, recording_url),
            audio=audio,
        )
        with pytest.raises(ProviderRequestError, match=message):
            unsafe_service.fetch_recording(**request)


def test_recording_fetch_rejects_absent_canonical_call_or_attempt(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    signer = RecordingCapabilitySigner("https://api.veramove.example", "r" * 32)
    recording_url = signer.build_url(attempt.call_id, attempt.job_id)
    snapshot = ConversationRepairSnapshot(
        conversation_id=attempt.reference.conversation_id,
        agent_id=attempt.expected_agent_id,
        status="done",
        has_audio=True,
    )
    signature = str(recording_url).split("signature=", 1)[1]
    service, _, conversations, _ = make_operator_service(
        attempt=attempt,
        signer=signer,
        snapshot=snapshot,
    )
    with pytest.raises(ResourceNotFound, match="Canonical call"):
        service.fetch_recording(attempt.call_id, attempt.job_id, signature)
    assert conversations.requests == []

    lookup = StaticCallLookup(calls=[make_call(attempt, recording_url)])
    service = LiveVoiceOperatorService(
        calls=lookup,
        signer=signer,
        conversations=StaticConversationClient(snapshot),
        recordings=StaticRecordingClient(
            RecordingAudio(content=b"synthetic", media_type="audio/mpeg")
        ),
        operator_secret=OPERATOR_SECRET,
    )
    with pytest.raises(ResourceNotFound, match="Call attempt"):
        service.fetch_recording(attempt.call_id, attempt.job_id, signature)


def test_repair_returns_done_event_without_materializing_or_persisting(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    signer = RecordingCapabilitySigner("https://api.veramove.example", "r" * 32)
    event = make_completed_event(attempt)
    snapshot = ConversationRepairSnapshot(
        conversation_id=attempt.reference.conversation_id,
        agent_id=attempt.expected_agent_id,
        status="done",
        has_audio=True,
        completed_event=event,
    )
    service, lookup, conversations, _ = make_operator_service(
        attempt=attempt,
        signer=signer,
        snapshot=snapshot,
    )

    result = service.prepare_repair(attempt.call_id, OPERATOR_SECRET)

    assert isinstance(result, CompletedConversationRepairInput)
    assert result.attempt == attempt
    assert result.event.idempotency_key != event.idempotency_key
    assert result.event.idempotency_key == service.prepare_repair(
        attempt.call_id,
        OPERATOR_SECRET,
    ).event.idempotency_key
    assert lookup.calls == []
    assert conversations.requests == [attempt.reference.conversation_id] * 2
    assert "phone" not in result.model_dump_json().lower()


def test_repair_returns_safe_failed_input_and_rejects_partial_states(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    signer = RecordingCapabilitySigner("https://api.veramove.example", "r" * 32)
    failed_snapshot = ConversationRepairSnapshot(
        conversation_id=attempt.reference.conversation_id,
        agent_id=attempt.expected_agent_id,
        status="failed",
        has_audio=False,
    )
    service, _, _, _ = make_operator_service(
        attempt=attempt,
        signer=signer,
        snapshot=failed_snapshot,
    )

    result = service.prepare_repair(attempt.call_id, OPERATOR_SECRET)

    assert isinstance(result, FailedConversationRepairInput)
    assert result.attempt == attempt
    assert result.idempotency_key == service.prepare_repair(
        attempt.call_id,
        OPERATOR_SECRET,
    ).idempotency_key
    assert result.failure_code == "provider_conversation_failed"
    assert "analysis" not in result.model_dump_json().lower()

    for status in ("initiated", "in-progress", "processing"):
        partial_service, _, _, _ = make_operator_service(
            attempt=attempt,
            signer=signer,
            snapshot=failed_snapshot.model_copy(update={"status": status}),
        )
        with pytest.raises(DomainConflict, match="not repairable"):
            partial_service.prepare_repair(attempt.call_id, OPERATOR_SECRET)


def test_repair_operator_secret_is_strong_constant_time_and_redacted(
    job_spec,
    fixtures,
    monkeypatch,
):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    signer = RecordingCapabilitySigner("https://api.veramove.example", "r" * 32)
    snapshot = ConversationRepairSnapshot(
        conversation_id=attempt.reference.conversation_id,
        agent_id=attempt.expected_agent_id,
        status="failed",
    )
    with pytest.raises(ProviderConfigurationError, match="VOICE_OPERATOR_SECRET"):
        LiveVoiceOperatorService(
            calls=StaticCallLookup(attempts=[attempt]),
            signer=signer,
            conversations=StaticConversationClient(snapshot),
            recordings=StaticRecordingClient(
                RecordingAudio(content=b"synthetic", media_type="audio/mpeg")
            ),
            operator_secret="short",
        )

    service, lookup, conversations, _ = make_operator_service(
        attempt=attempt,
        signer=signer,
        snapshot=snapshot,
    )
    comparisons: list[tuple[bytes, bytes]] = []

    def record_comparison(left: bytes, right: bytes) -> bool:
        comparisons.append((left, right))
        return False

    monkeypatch.setattr(live_voice_operator.hmac, "compare_digest", record_comparison)
    supplied = "x" * 32
    with pytest.raises(WebhookAuthenticationError) as exc_info:
        service.prepare_repair(attempt.call_id, supplied)

    assert comparisons == [(OPERATOR_SECRET.encode(), supplied.encode())]
    assert OPERATOR_SECRET not in str(exc_info.value)
    assert supplied not in str(exc_info.value)
    assert lookup.attempt_requests == []
    assert conversations.requests == []
