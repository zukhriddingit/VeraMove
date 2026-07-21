"""Fail-closed tests for the controlled ElevenLabs outbound-call adapter."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from services.api.app.api.dependencies import build_service
from services.api.app.contracts import (
    CallContext,
    CallStatus,
    FeeCategory,
    JobState,
    VendorCallPlanQuestionV1,
    VendorCallPlanV1,
)
from services.api.app.core.config import LiveVoiceConfig, Settings, SupabaseConfig
from services.api.app.core.errors import (
    ProviderConfigurationError,
    ProviderRequestError,
    ResourceNotFound,
)
from services.api.app.integrations.elevenlabs.conversations import (
    ElevenLabsConversationClient,
)
from services.api.app.integrations.elevenlabs.live import ElevenLabsVoiceProvider
from services.api.app.integrations.elevenlabs.recordings import (
    ElevenLabsRecordingClient,
)
from services.api.app.orchestration.models import job_spec_sha256
from services.api.app.orchestration.providers import VoiceCallDestination
from services.api.app.repositories.memory import InMemoryRepository


class RecordingTransport:
    """Capture JSON requests without opening a socket."""

    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.requests.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


class RaisingTransport:
    """Raise a controlled provider error without opening a socket."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.requests = 0

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        del url, headers, payload, timeout_seconds
        self.requests += 1
        raise self.error


class RecordingConversationTransport:
    def __init__(
        self,
        *,
        details: object | None = None,
        audio: bytes = b"synthetic-audio",
        media_type: str = "audio/mpeg",
    ) -> None:
        self.details = details
        self.audio = audio
        self.media_type = media_type
        self.json_requests: list[tuple[str, dict[str, str], float]] = []
        self.audio_requests: list[tuple[str, dict[str, str], float]] = []

    def get_json(
        self,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.json_requests.append((url, headers, timeout_seconds))
        return self.details  # type: ignore[return-value]

    def get_bytes(
        self,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> tuple[bytes, str]:
        self.audio_requests.append((url, headers, timeout_seconds))
        return self.audio, self.media_type


@pytest.fixture
def live_settings() -> Settings:
    return Settings(
        app_mode="live",
        live_voice=LiveVoiceConfig(
            api_key="synthetic-api-key",
            intake_agent_id="synthetic-intake-agent",
            outbound_agent_id="synthetic-outbound-agent",
            phone_number_id="synthetic-phone-id",
            destination_numbers=(
                "+15550100001",
                "+15550100002",
                "+15550100003",
            ),
            webhook_secret="w" * 32,
            precall_secret="p" * 32,
            recording_signing_secret="r" * 32,
            operator_secret="o" * 32,
            public_api_base_url="https://api.veramove.example",
            agent_config_version="2026-07-19.1",
            live_calls_enabled=True,
        ),
        supabase=SupabaseConfig(
            enabled=True,
            url="https://synthetic-project.supabase.co",
            secret_key="synthetic-supabase-secret",
        ),
    )


def test_settings_default_to_safe_mock_with_empty_live_values(monkeypatch):
    for name in (
        "APP_MODE",
        "LIVE_CALLS_ENABLED",
        "ELEVENLABS_API_KEY",
        "ELEVENLABS_INTAKE_AGENT_ID",
        "ELEVENLABS_OUTBOUND_AGENT_ID",
        "ELEVENLABS_QUOTE_AGENT_ID",
        "ELEVENLABS_NEGOTIATOR_AGENT_ID",
        "ELEVENLABS_PHONE_NUMBER_ID",
        "ELEVENLABS_WEBHOOK_SECRET",
        "ELEVENLABS_PRECALL_SECRET",
        "ELEVENLABS_API_BASE_URL",
        "LIVE_TEST_TO_NUMBERS",
        "LIVE_TEST_TO_NUMBER",
        "PUBLIC_API_BASE_URL",
        "RECORDING_SIGNING_SECRET",
        "VOICE_OPERATOR_SECRET",
        "AGENT_CONFIG_VERSION",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.app_mode == "mock"
    assert settings.live_voice.live_calls_enabled is False
    assert settings.live_voice.api_key is None
    assert settings.live_voice.destination_numbers == ()


def test_settings_cors_origins_default_and_explicit_override(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    assert Settings.from_env().cors_allow_origins == (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )

    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        " https://veramove-demo.example,https://preview.veramove-demo.example/ ",
    )
    assert Settings.from_env().cors_allow_origins == (
        "https://veramove-demo.example",
        "https://preview.veramove-demo.example",
    )


@pytest.mark.parametrize(
    "value",
    ["*", "https://veramove-demo.example/path", "veramove-demo.example"],
)
def test_settings_reject_invalid_cors_origins(monkeypatch, value):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", value)
    with pytest.raises(ProviderConfigurationError, match="CORS_ALLOW_ORIGINS"):
        Settings.from_env()


@pytest.mark.parametrize("enabled", ["1", "true", "TRUE", "yes", "on"])
def test_settings_parse_explicit_true_values(monkeypatch, enabled):
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("LIVE_CALLS_ENABLED", enabled)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "   ")

    settings = Settings.from_env()

    assert settings.live_voice.live_calls_enabled is True
    assert settings.live_voice.api_key is None


@pytest.mark.parametrize("disabled", ["0", "false", "FALSE", "no", "off"])
def test_settings_parse_explicit_false_values(monkeypatch, disabled):
    monkeypatch.setenv("LIVE_CALLS_ENABLED", disabled)

    assert Settings.from_env().live_voice.live_calls_enabled is False


def test_settings_reject_invalid_mode_and_boolean(monkeypatch):
    monkeypatch.setenv("APP_MODE", "unexpected")
    with pytest.raises(ProviderConfigurationError, match="APP_MODE"):
        Settings.from_env()

    monkeypatch.setenv("APP_MODE", "mock")
    monkeypatch.setenv("LIVE_CALLS_ENABLED", "maybe")
    with pytest.raises(ProviderConfigurationError, match="LIVE_CALLS_ENABLED"):
        Settings.from_env()


def test_live_provider_does_not_send_when_switch_is_disabled(
    live_settings,
    fixtures,
    job_spec,
):
    transport = RecordingTransport({"success": True, "conversation_id": "conv-1", "callSid": "CA1"})
    disabled = replace(
        live_settings,
        live_voice=replace(
            live_settings.live_voice,
            live_calls_enabled=False,
        ),
    )
    provider = ElevenLabsVoiceProvider(disabled, transport)

    with pytest.raises(ProviderConfigurationError, match="LIVE_CALLS_ENABLED"):
        provider.initiate_quote_call(
            job_spec,
            fixtures.load_vendors()[0],
            uuid4(),
        )

    assert transport.requests == []


def test_live_provider_does_not_send_with_missing_configuration(fixtures, job_spec):
    transport = RecordingTransport({"success": True, "conversation_id": "conv-1", "callSid": "CA1"})
    provider = ElevenLabsVoiceProvider(
        Settings(
            app_mode="live",
            live_voice=LiveVoiceConfig(live_calls_enabled=True),
            supabase=SupabaseConfig(
                enabled=True,
                url="https://synthetic-project.supabase.co",
                secret_key="synthetic-supabase-secret",
            ),
        ),
        transport,
    )

    with pytest.raises(ProviderConfigurationError) as exc_info:
        provider.initiate_quote_call(
            job_spec,
            fixtures.load_vendors()[0],
            uuid4(),
        )

    message = str(exc_info.value)
    assert "ELEVENLABS_API_KEY" in message
    assert "ELEVENLABS_INTAKE_AGENT_ID" in message
    assert "ELEVENLABS_OUTBOUND_AGENT_ID" in message
    assert "ELEVENLABS_PHONE_NUMBER_ID" in message
    assert "PUBLIC_API_BASE_URL" in message
    assert "AGENT_CONFIG_VERSION" in message
    assert transport.requests == []


def test_live_service_construction_does_not_validate_or_send():
    transport = RecordingTransport({"success": True, "conversation_id": "conv-1", "callSid": "CA1"})

    build_service(
        Settings(app_mode="live"),
        InMemoryRepository(),
        voice_transport=transport,
    )

    assert transport.requests == []


def test_live_provider_builds_native_outbound_payload(
    live_settings,
    fixtures,
    job_spec,
):
    transport = RecordingTransport({"success": True, "conversation_id": "conv-1", "callSid": "CA1"})
    provider = ElevenLabsVoiceProvider(live_settings, transport)
    call_id = uuid4()

    result = provider.initiate_quote_call(
        job_spec,
        fixtures.load_vendors()[0],
        call_id,
        1,
    )

    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request["url"] == ("https://api.elevenlabs.io/v1/convai/twilio/outbound-call")
    assert request["headers"] == {
        "xi-api-key": "synthetic-api-key",
        "content-type": "application/json",
    }
    assert request["timeout_seconds"] == 10.0
    payload = request["payload"]
    assert isinstance(payload, dict)
    assert payload["agent_id"] == "synthetic-outbound-agent"
    assert payload["agent_phone_number_id"] == "synthetic-phone-id"
    assert payload["to_number"] == "+15550100002"
    assert payload["call_recording_enabled"] is True
    dynamic_variables = payload["conversation_initiation_client_data"]["dynamic_variables"]
    assert dynamic_variables["job_id"] == str(job_spec.job_id)
    assert dynamic_variables["call_id"] == str(call_id)
    assert dynamic_variables["call_mode"] == "quote"
    assert dynamic_variables["job_spec_version"] == job_spec.version
    assert dynamic_variables["agent_config_version"] == "2026-07-19.1"
    assert dynamic_variables["vendor_name"] == "ClearPath Movers"
    assert dynamic_variables["verified_competitor_quote_id"] == ""
    assert dynamic_variables["verified_competitor_total"] == ""
    assert dynamic_variables["verified_competitor_evidence_json"] == ""
    assert dynamic_variables["negotiation_objective"] == ""
    assert json.loads(dynamic_variables["job_spec_json"])["job_id"] == str(job_spec.job_id)
    assert result.reference.conversation_id == "conv-1"
    assert result.reference.provider_call_id == "CA1"
    assert result.outcome is None


def test_live_provider_selects_negotiator_and_verified_leverage(
    live_settings,
    fixtures,
    job_spec,
):
    transport = RecordingTransport({"success": True, "conversation_id": "conv-2", "callSid": "CA2"})
    provider = ElevenLabsVoiceProvider(live_settings, transport)
    competitor = fixtures.load_initial_quotes()[0]
    planned = fixtures.load_negotiated_quote()

    provider.initiate_negotiation_call(
        job_spec,
        planned.vendor,
        competitor,
        planned,
        uuid4(),
        2,
    )

    payload = transport.requests[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["agent_id"] == "synthetic-outbound-agent"
    assert payload["to_number"] == "+15550100003"
    variables = payload["conversation_initiation_client_data"]["dynamic_variables"]
    assert variables["call_mode"] == "negotiation"
    assert variables["verified_competitor_quote_id"] == str(competitor.quote_id)
    assert variables["verified_competitor_total"] == str(competitor.comparable_total)
    assert json.loads(variables["verified_competitor_evidence_json"])["evidence_ids"] == [
        str(item.evidence_id) for item in competitor.transcript_evidence
    ]
    objective = json.loads(variables["negotiation_objective"])
    assert objective == {
        "concessions": planned.concessions,
        "currency": planned.currency,
        "target_total": str(planned.negotiated_total),
    }


def test_live_provider_uses_authorized_destination_and_research_plan(
    live_settings,
    fixtures,
    job_spec,
):
    settings = replace(
        live_settings,
        live_voice=replace(
            live_settings.live_voice,
            real_vendor_calls_enabled=True,
            contact_hash_secret="h" * 32,
        ),
    )
    transport = RecordingTransport(
        {"success": True, "conversation_id": "conv-real", "callSid": "CA-real"}
    )
    provider = ElevenLabsVoiceProvider(settings, transport)
    vendor = fixtures.load_vendors()[0]
    plan = VendorCallPlanV1(
        vendor_id=vendor.vendor_id,
        job_spec_version=job_spec.version,
        job_spec_sha256=job_spec_sha256(job_spec),
        questions=[
            VendorCallPlanQuestionV1(
                question_id=uuid4(),
                category=FeeCategory.TRAVEL.value,
                question="What travel fee applies to this exact move?",
                reason="missing_information",
            )
        ],
    )
    destination = VoiceCallDestination(
        call_context=CallContext.OFFICIAL_BUSINESS,
        destination_slot=0,
        authorization_id=uuid4(),
        normalized_number="+16175550101",
        number_hash="a" * 64,
        recording_consented=True,
    )

    provider.initiate_quote_call(
        job_spec,
        vendor,
        uuid4(),
        destination,
        plan,
    )

    payload = transport.requests[0]["payload"]
    assert payload["to_number"] == "+16175550101"
    assert payload["call_recording_enabled"] is True
    variables = payload["conversation_initiation_client_data"]["dynamic_variables"]
    assert variables["call_context"] == "official_business"
    assert json.loads(variables["vendor_call_plan_json"])["vendor_id"] == str(
        vendor.vendor_id
    )
    assert json.loads(variables["website_claims_json"]) == []
    assert json.loads(variables["verification_questions_json"])[0][
        "category"
    ] == FeeCategory.TRAVEL.value
    assert "+16175550101" not in json.dumps(variables)


def test_live_provider_uses_zero_comparable_total_without_truthiness_fallback(
    live_settings,
    fixtures,
    job_spec,
):
    transport = RecordingTransport(
        {"success": True, "conversation_id": "conv-zero", "callSid": "CA-zero"}
    )
    provider = ElevenLabsVoiceProvider(live_settings, transport)
    competitor = fixtures.load_initial_quotes()[0].model_copy(
        update={
            "comparable_total": Decimal("0.00"),
            "negotiated_total": Decimal("999.00"),
        }
    )

    provider.initiate_negotiation_call(
        job_spec,
        fixtures.load_negotiated_quote().vendor,
        competitor,
        fixtures.load_negotiated_quote(),
        uuid4(),
        0,
    )

    payload = transport.requests[0]["payload"]
    assert isinstance(payload, dict)
    variables = payload["conversation_initiation_client_data"]["dynamic_variables"]
    assert variables["verified_competitor_total"] == "0.00"


@pytest.mark.parametrize("invalid_slot", (-1, 3, True))
def test_live_provider_rejects_invalid_destination_slot_before_transport(
    invalid_slot,
    live_settings,
    fixtures,
    job_spec,
):
    transport = RecordingTransport({"success": True, "conversation_id": "conv-1", "callSid": "CA1"})
    provider = ElevenLabsVoiceProvider(live_settings, transport)

    with pytest.raises(ProviderRequestError, match="destination slot"):
        provider.initiate_quote_call(
            job_spec,
            fixtures.load_vendors()[0],
            uuid4(),
            invalid_slot,
        )

    assert transport.requests == []


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ({"success": False}, "rejected"),
        ({"success": True, "callSid": "CA1"}, "conversation_id"),
        ({"success": True, "conversation_id": "conv-1"}, "callSid"),
        (
            {"success": True, "conversation_id": "  ", "callSid": "CA1"},
            "conversation_id",
        ),
    ],
)
def test_live_provider_rejects_invalid_responses(
    response,
    message,
    live_settings,
    fixtures,
    job_spec,
):
    provider = ElevenLabsVoiceProvider(live_settings, RecordingTransport(response))

    with pytest.raises(ProviderRequestError, match=message):
        provider.initiate_quote_call(
            job_spec,
            fixtures.load_vendors()[0],
            uuid4(),
        )


def test_live_service_routes_exactly_three_identical_snapshots_to_distinct_slots(
    live_settings,
    job_spec,
):
    transport = RecordingTransport({"success": True, "conversation_id": "conv-1", "callSid": "CA1"})
    service = build_service(
        live_settings,
        InMemoryRepository(),
        voice_transport=transport,
    )
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)

    result = service.initiate_quote_batch(job_spec.job_id)

    assert result.state is JobState.CALLING
    assert len(transport.requests) == 3
    payloads = [request["payload"] for request in transport.requests]
    assert all(isinstance(payload, dict) for payload in payloads)
    assert {payload["to_number"] for payload in payloads} == {
        "+15550100001",
        "+15550100002",
        "+15550100003",
    }
    assert {payload["agent_id"] for payload in payloads} == {"synthetic-outbound-agent"}
    dynamic_variables = [
        payload["conversation_initiation_client_data"]["dynamic_variables"] for payload in payloads
    ]
    assert {item["call_mode"] for item in dynamic_variables} == {"quote"}
    assert len({item["job_spec_json"] for item in dynamic_variables}) == 1
    assert len({item["job_spec_sha256"] for item in dynamic_variables}) == 1
    attempts = service.list_call_attempts(job_spec.job_id)
    assert len(attempts) == 3
    assert {attempt.destination_slot for attempt in attempts} == {0, 1, 2}
    assert len({attempt.job_spec_sha256 for attempt in attempts}) == 1
    assert {attempt.expected_agent_id for attempt in attempts} == {"synthetic-outbound-agent"}
    assert {attempt.agent_config_version for attempt in attempts} == {"2026-07-19.1"}
    assert all(attempt.status is CallStatus.IN_PROGRESS for attempt in attempts)


def test_live_transport_failure_preserves_failed_attempt(
    live_settings,
    job_spec,
):
    transport = RaisingTransport(ProviderRequestError("synthetic failure"))
    service = build_service(
        live_settings,
        InMemoryRepository(),
        voice_transport=transport,
    )
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)

    result = service.initiate_quote_batch(job_spec.job_id)

    attempts = service.list_call_attempts(job_spec.job_id)
    assert transport.requests == 3
    assert len(attempts) == 3
    assert all(attempt.status is CallStatus.FAILED for attempt in attempts)
    assert all(attempt.completed_at is not None for attempt in attempts)
    assert result.state is JobState.QUOTES_READY
    assert len(result.calls) == 3
    assert all(call.status is CallStatus.FAILED for call in result.calls)
    assert all(call.recording_url is None for call in result.calls)


def test_conversation_client_returns_only_safe_repair_fields():
    details = {
        "conversation_id": "conv_synthetic_repair",
        "agent_id": "agent_synthetic_outbound",
        "status": "done",
        "has_audio": True,
        "metadata": {"phone_call": {"external_number": "+15550100001"}},
        "analysis": {"data_collection_results": {}},
        "transcript": [],
    }
    transport = RecordingConversationTransport(details=details)
    client = ElevenLabsConversationClient(
        api_key="synthetic-elevenlabs-secret",
        api_base_url="https://api.elevenlabs.example",
        transport=transport,
        clock=lambda: datetime(2026, 7, 19, 12, 0, tzinfo=UTC),
    )

    snapshot = client.fetch_for_repair("conv_synthetic_repair")

    assert snapshot.status == "done"
    assert snapshot.has_audio is True
    assert snapshot.completed_event is not None
    assert snapshot.completed_event.conversation_id == "conv_synthetic_repair"
    assert "+15550100001" not in snapshot.model_dump_json()
    assert transport.json_requests == [
        (
            "https://api.elevenlabs.example/v1/convai/conversations/conv_synthetic_repair",
            {"xi-api-key": "synthetic-elevenlabs-secret"},
            15.0,
        )
    ]


@pytest.mark.parametrize("status", ("initiated", "in-progress", "processing", "failed"))
def test_conversation_client_preserves_partial_or_failed_status_without_analysis(status):
    transport = RecordingConversationTransport(
        details={
            "conversation_id": "conv_synthetic_partial",
            "agent_id": "agent_synthetic_outbound",
            "status": status,
            "analysis": {"data_collection_results": {"outcome_type": "discard"}},
        }
    )

    snapshot = ElevenLabsConversationClient(
        api_key="synthetic-secret",
        transport=transport,
    ).fetch_for_repair("conv_synthetic_partial")

    assert snapshot.status == status
    assert snapshot.completed_event is None


@pytest.mark.parametrize(
    "details",
    (
        [],
        {"conversation_id": "wrong", "agent_id": "agent", "status": "done"},
        {"conversation_id": "conv_valid", "agent_id": "", "status": "done"},
        {"conversation_id": "conv_valid", "agent_id": "agent", "status": "mystery"},
    ),
)
def test_conversation_client_rejects_invalid_provider_details(details):
    client = ElevenLabsConversationClient(
        api_key="synthetic-secret",
        transport=RecordingConversationTransport(details=details),
    )

    with pytest.raises(ProviderRequestError):
        client.fetch_for_repair("conv_valid")


def test_recording_client_fetches_allowlisted_audio_without_exposing_key():
    transport = RecordingConversationTransport(
        audio=b"synthetic-mpeg-bytes",
        media_type="audio/mpeg; charset=binary",
    )
    client = ElevenLabsRecordingClient(
        api_key="synthetic-elevenlabs-secret",
        api_base_url="https://api.elevenlabs.example",
        transport=transport,
    )

    audio = client.fetch_audio("conv_synthetic_audio", has_audio=True)

    assert audio.content == b"synthetic-mpeg-bytes"
    assert audio.media_type == "audio/mpeg"
    assert transport.audio_requests == [
        (
            "https://api.elevenlabs.example/v1/convai/conversations/conv_synthetic_audio/audio",
            {"xi-api-key": "synthetic-elevenlabs-secret"},
            30.0,
        )
    ]


def test_recording_client_rejects_absent_empty_or_wrong_type_audio():
    no_audio_transport = RecordingConversationTransport()
    client = ElevenLabsRecordingClient(
        api_key="synthetic-secret",
        transport=no_audio_transport,
    )
    with pytest.raises(ResourceNotFound, match="no saved recording"):
        client.fetch_audio("conv_synthetic_audio", has_audio=False)
    assert no_audio_transport.audio_requests == []

    with pytest.raises(ResourceNotFound, match="empty"):
        ElevenLabsRecordingClient(
            api_key="synthetic-secret",
            transport=RecordingConversationTransport(audio=b""),
        ).fetch_audio("conv_synthetic_audio", has_audio=True)

    with pytest.raises(ProviderRequestError, match="unsupported recording type"):
        ElevenLabsRecordingClient(
            api_key="synthetic-secret",
            transport=RecordingConversationTransport(media_type="text/html"),
        ).fetch_audio("conv_synthetic_audio", has_audio=True)
