"""Safe application-scoped integration-status wiring tests."""

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from services.api.app.api.dependencies import (
    build_repository,
    build_service,
    get_integration_status,
)
from services.api.app.api.integration_status import IntegrationStatusReporter
from services.api.app.core.config import (
    LiveVoiceConfig,
    OpenAIConfig,
    Settings,
    SupabaseConfig,
    TavilyConfig,
)
from services.api.app.main import create_app
from services.api.app.observability.usage import UsageRecord, UsageRecorder


def test_mock_apps_get_distinct_credential_free_usage_recorders() -> None:
    first = create_app(Settings())
    second = create_app(Settings())

    first_reporter = first.state.service._integration_status
    second_reporter = second.state.service._integration_status

    assert first_reporter.usage_recorder is not second_reporter.usage_recorder
    snapshot = first_reporter.snapshot()
    assert snapshot.openai.enabled is False
    assert snapshot.openai.configured is False
    assert snapshot.openai.usage == ()
    assert snapshot.tavily.model_dump() == {"enabled": False, "configured": False}
    assert snapshot.supabase.model_dump() == {"enabled": False, "configured": False}
    assert snapshot.live_voice.model_dump() == {"enabled": False, "configured": False}

    with TestClient(first) as client:
        response = client.get("/api/integrations/status")

    assert response.status_code == 200
    assert response.json() == snapshot.model_dump(mode="json")


def test_build_service_injects_one_recorder_into_both_openai_clients() -> None:
    recorder = UsageRecorder()
    settings = Settings(
        openai=OpenAIConfig(
            enabled=True,
            api_key="synthetic-secret-key",
            document_model="gpt-document-synthetic",
            recommendation_model="gpt-narrative-synthetic",
        )
    )
    service = build_service(
        settings,
        build_repository(settings),
        usage_recorder=recorder,
    )

    document_client = service._intelligence._document_gateway._client
    narrative_client = service._recommendation_narrator._client

    assert document_client._usage_recorder is recorder
    assert narrative_client._usage_recorder is recorder
    assert service._integration_status.usage_recorder is recorder


def test_status_aggregates_only_safe_usage_and_provider_booleans() -> None:
    api_secret = "SYNTHETIC_OPENAI_SECRET_MARKER"
    destination = "+12025550101"
    settings = Settings(
        app_mode="mock",
        live_voice=LiveVoiceConfig(
            api_key="synthetic-elevenlabs-secret",
            intake_agent_id="synthetic-intake-agent",
            outbound_agent_id="synthetic-outbound-agent",
            phone_number_id="synthetic-phone-number",
            destination_numbers=(destination, "+12025550102", "+12025550103"),
            webhook_secret="w" * 32,
            precall_secret="p" * 32,
            recording_signing_secret="r" * 32,
            operator_secret="o" * 32,
            public_api_base_url="https://api.veramove.example",
            agent_config_version="synthetic-v1",
            live_calls_enabled=False,
        ),
        openai=OpenAIConfig(enabled=False, api_key=api_secret),
        tavily=TavilyConfig(enabled=False, api_key="synthetic-tavily-secret"),
        supabase=SupabaseConfig(
            enabled=False,
            url="https://synthetic-project.supabase.co",
            secret_key="synthetic-supabase-secret",
        ),
    )
    recorder = UsageRecorder()
    recorder.record(
        UsageRecord(
            capability="document_extraction",
            model="gpt-synthetic-model",
            input_tokens=12,
            output_tokens=3,
            total_tokens=15,
            latency_ms=42,
            success_category="success",
            provider_request_id="provider-private-request-id",
        )
    )
    recorder.record(
        UsageRecord(
            capability="document_extraction",
            model="gpt-synthetic-model",
            input_tokens=4,
            output_tokens=0,
            total_tokens=4,
            latency_ms=8,
            success_category="provider_error",
        )
    )
    service = build_service(
        settings,
        build_repository(settings),
        usage_recorder=recorder,
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(service=service))
    )

    snapshot = get_integration_status(request)
    serialized = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True)

    assert snapshot.openai.enabled is False
    assert snapshot.openai.configured is True
    assert snapshot.tavily.configured is True
    assert snapshot.supabase.configured is True
    assert snapshot.live_voice.configured is True
    assert len(snapshot.openai.usage) == 1
    usage = snapshot.openai.usage[0]
    assert usage.model_dump() == {
        "capability": "document_extraction",
        "model": "gpt-synthetic-model",
        "request_count": 2,
        "successful_requests": 1,
        "failed_requests": 1,
        "input_tokens": 16,
        "output_tokens": 3,
        "total_tokens": 19,
        "total_latency_ms": 50,
    }
    for sensitive in (
        api_secret,
        destination,
        "synthetic-tavily-secret",
        "synthetic-supabase-secret",
        "provider-private-request-id",
        "synthetic-intake-agent",
        "synthetic-phone-number",
    ):
        assert sensitive not in serialized


def test_enabled_but_incomplete_provider_reports_not_configured() -> None:
    settings = Settings(
        app_mode="live",
        openai=OpenAIConfig(enabled=True, api_key=None),
        tavily=TavilyConfig(enabled=True, api_key=None),
        supabase=SupabaseConfig(enabled=True, url=None, secret_key=None),
        live_voice=LiveVoiceConfig(live_calls_enabled=True),
    )

    snapshot = IntegrationStatusReporter(settings, UsageRecorder()).snapshot()

    assert snapshot.openai.model_dump(exclude={"usage"}) == {
        "enabled": True,
        "configured": False,
    }
    assert snapshot.tavily.model_dump() == {"enabled": True, "configured": False}
    assert snapshot.supabase.model_dump() == {"enabled": True, "configured": False}
    assert snapshot.live_voice.model_dump() == {"enabled": True, "configured": False}
