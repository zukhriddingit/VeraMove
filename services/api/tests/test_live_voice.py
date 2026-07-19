"""Fail-closed tests for the controlled ElevenLabs outbound-call adapter."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest

from services.api.app.api.dependencies import build_service
from services.api.app.contracts import CallStatus, JobState
from services.api.app.core.config import LiveVoiceConfig, Settings
from services.api.app.core.errors import (
    ProviderConfigurationError,
    ProviderRequestError,
)
from services.api.app.integrations.elevenlabs.live import ElevenLabsVoiceProvider
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


@pytest.fixture
def live_settings() -> Settings:
    return Settings(
        app_mode="live",
        live_voice=LiveVoiceConfig(
            api_key="synthetic-api-key",
            quote_agent_id="synthetic-quote-agent",
            negotiator_agent_id="synthetic-negotiator-agent",
            phone_number_id="synthetic-phone-id",
            test_to_number="+15550100000",
            webhook_secret="synthetic-webhook-secret",
            live_calls_enabled=True,
        ),
    )


def test_settings_default_to_safe_mock_with_empty_live_values(monkeypatch):
    for name in (
        "APP_MODE",
        "LIVE_CALLS_ENABLED",
        "ELEVENLABS_API_KEY",
        "ELEVENLABS_QUOTE_AGENT_ID",
        "ELEVENLABS_NEGOTIATOR_AGENT_ID",
        "ELEVENLABS_PHONE_NUMBER_ID",
        "ELEVENLABS_WEBHOOK_SECRET",
        "ELEVENLABS_API_BASE_URL",
        "LIVE_TEST_TO_NUMBER",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.app_mode == "mock"
    assert settings.live_voice.live_calls_enabled is False
    assert settings.live_voice.api_key is None
    assert settings.live_voice.test_to_number is None


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
    transport = RecordingTransport(
        {"success": True, "conversation_id": "conv-1", "callSid": "CA1"}
    )
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
    transport = RecordingTransport(
        {"success": True, "conversation_id": "conv-1", "callSid": "CA1"}
    )
    provider = ElevenLabsVoiceProvider(
        Settings(
            app_mode="live",
            live_voice=LiveVoiceConfig(live_calls_enabled=True),
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
    assert "ELEVENLABS_QUOTE_AGENT_ID" in message
    assert "ELEVENLABS_NEGOTIATOR_AGENT_ID" in message
    assert "ELEVENLABS_PHONE_NUMBER_ID" in message
    assert "ELEVENLABS_WEBHOOK_SECRET" in message
    assert "LIVE_TEST_TO_NUMBER" in message
    assert transport.requests == []


def test_live_service_construction_does_not_validate_or_send():
    transport = RecordingTransport(
        {"success": True, "conversation_id": "conv-1", "callSid": "CA1"}
    )

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
    transport = RecordingTransport(
        {"success": True, "conversation_id": "conv-1", "callSid": "CA1"}
    )
    provider = ElevenLabsVoiceProvider(live_settings, transport)
    call_id = uuid4()

    result = provider.initiate_quote_call(
        job_spec,
        fixtures.load_vendors()[0],
        call_id,
    )

    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request["url"] == (
        "https://api.elevenlabs.io/v1/convai/twilio/outbound-call"
    )
    assert request["headers"] == {
        "xi-api-key": "synthetic-api-key",
        "content-type": "application/json",
    }
    assert request["timeout_seconds"] == 10.0
    payload = request["payload"]
    assert isinstance(payload, dict)
    assert payload["agent_id"] == "synthetic-quote-agent"
    assert payload["agent_phone_number_id"] == "synthetic-phone-id"
    assert payload["to_number"] == "+15550100000"
    assert payload["call_recording_enabled"] is True
    dynamic_variables = payload["conversation_initiation_client_data"][
        "dynamic_variables"
    ]
    assert dynamic_variables["job_id"] == str(job_spec.job_id)
    assert dynamic_variables["call_id"] == str(call_id)
    assert dynamic_variables["vendor_name"] == "ClearPath Movers"
    assert json.loads(dynamic_variables["job_spec_json"])["job_id"] == str(
        job_spec.job_id
    )
    assert result.reference.conversation_id == "conv-1"
    assert result.reference.provider_call_id == "CA1"
    assert result.outcome is None


def test_live_provider_selects_negotiator_and_verified_leverage(
    live_settings,
    fixtures,
    job_spec,
):
    transport = RecordingTransport(
        {"success": True, "conversation_id": "conv-2", "callSid": "CA2"}
    )
    provider = ElevenLabsVoiceProvider(live_settings, transport)
    competitor = fixtures.load_initial_quotes()[0]
    planned = fixtures.load_negotiated_quote()

    provider.initiate_negotiation_call(
        job_spec,
        planned.vendor,
        competitor,
        planned,
        uuid4(),
    )

    payload = transport.requests[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["agent_id"] == "synthetic-negotiator-agent"
    variables = payload["conversation_initiation_client_data"]["dynamic_variables"]
    assert variables["verified_competitor_quote_id"] == str(competitor.quote_id)
    assert variables["verified_competitor_total"] == str(
        competitor.negotiated_total
    )
    assert variables["target_vendor_name"] == planned.vendor.name
    objective = json.loads(variables["planned_objective"])
    assert objective == {
        "concessions": planned.concessions,
        "currency": planned.currency,
        "target_total": str(planned.negotiated_total),
    }


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


def test_live_service_limits_calls_route_to_one_request(
    live_settings,
    job_spec,
):
    transport = RecordingTransport(
        {"success": True, "conversation_id": "conv-1", "callSid": "CA1"}
    )
    service = build_service(
        live_settings,
        InMemoryRepository(),
        voice_transport=transport,
    )
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)

    result = service.initiate_quote_batch(job_spec.job_id)

    assert result.state is JobState.CALLING
    assert len(transport.requests) == 1
    attempts = service.list_call_attempts(job_spec.job_id)
    assert len(attempts) == 1
    assert attempts[0].status is CallStatus.IN_PROGRESS


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

    with pytest.raises(ProviderRequestError, match="synthetic failure"):
        service.initiate_quote_batch(job_spec.job_id)

    attempts = service.list_call_attempts(job_spec.job_id)
    assert transport.requests == 1
    assert len(attempts) == 1
    assert attempts[0].status is CallStatus.FAILED
    assert attempts[0].completed_at is not None
    failed = service.get_job(job_spec.job_id)
    assert failed.state is JobState.FAILED
    assert failed.calls == []
