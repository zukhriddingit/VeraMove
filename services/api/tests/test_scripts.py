"""Developer command construction and live-operator safety tests."""

import json
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from scripts.bootstrap import venv_python
from scripts.check import build_check_steps
from scripts.generate_agent_assets import (
    GENERATED_ASSET_PATHS,
    generate_agent_assets,
)
from scripts.generate_agent_assets import (
    main as generate_agent_assets_main,
)
from scripts.live_voice_preflight import (
    INTAKE_DATA_COLLECTION_FIELDS,
    INTAKE_PROMPT_VARIABLES,
    OUTBOUND_DATA_COLLECTION_FIELDS,
    OUTBOUND_PROMPT_VARIABLES,
    HttpElevenLabsPreflightClient,
    ProviderReadiness,
    run_preflight,
)
from scripts.live_voice_smoke import run_supervised_smoke
from services.api.app.core.config import LiveVoiceConfig, Settings, SupabaseConfig
from services.api.app.orchestration.models import VoiceCallReference, VoiceCallResult


def test_bootstrap_uses_platform_venv_python(tmp_path):
    assert venv_python(tmp_path).name in {"python", "python.exe"}


def test_check_pipeline_has_required_order():
    assert [step.label for step in build_check_steps()] == [
        "Ruff",
        "pytest",
        "OpenAPI export",
        "API type generation",
        "frontend typecheck",
        "frontend tests",
        "frontend build",
    ]


def test_check_commands_are_root_relative():
    export = build_check_steps()[2]
    assert Path(export.command[1]) == Path("scripts/export_openapi.py")


def test_agent_asset_generator_is_deterministic_and_matches_committed_files(tmp_path):
    generated_root = tmp_path / "agents"
    generated_paths = generate_agent_assets(output_root=generated_root)

    assert [path.relative_to(generated_root) for path in generated_paths] == list(
        GENERATED_ASSET_PATHS
    )
    for relative_path in GENERATED_ASSET_PATHS:
        generated = (generated_root / relative_path).read_bytes()
        committed = (Path(__file__).resolve().parents[3] / "agents" / relative_path).read_bytes()
        assert generated == committed


def test_agent_asset_generator_prints_provider_shape_without_writing(
    monkeypatch,
    capsys,
    tmp_path,
):
    output_root = tmp_path / "must-not-be-created"
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_agent_assets.py",
            "--print-elevenlabs-data-collection",
            "outbound",
            "--output-root",
            str(output_root),
        ],
    )

    assert generate_agent_assets_main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["outcome_type"]["type"] == "string"
    assert set(payload["headline_total"]) == {"type", "description"}
    assert payload["recipient_opt_out"]["type"] == "boolean"
    assert len(payload) == 15
    assert not output_root.exists()


class FakeProviderPreflightClient:
    def __init__(self, result: ProviderReadiness) -> None:
        self.result = result
        self.calls = 0

    def inspect(self, _config: LiveVoiceConfig) -> ProviderReadiness:
        self.calls += 1
        return self.result


class FakeConnectivityClient:
    def __init__(self, reachable: bool) -> None:
        self.reachable = reachable
        self.calls = 0

    def is_reachable(self, _config) -> bool:
        self.calls += 1
        return self.reachable


def live_settings() -> Settings:
    return Settings(
        app_mode="live",
        live_voice=LiveVoiceConfig(
            api_key="elevenlabs-secret-value",
            intake_agent_id="agent-intake-secret-identifier",
            outbound_agent_id="agent-outbound-secret-identifier",
            phone_number_id="phone-number-secret-identifier",
            destination_numbers=("+12025550101", "+12025550102", "+12025550103"),
            webhook_secret="w" * 32,
            precall_secret="p" * 32,
            recording_signing_secret="r" * 32,
            operator_secret="o" * 32,
            public_api_base_url="https://veramove.example.com",
            agent_config_version="2026-07-21.2",
            live_calls_enabled=True,
        ),
        supabase=SupabaseConfig(
            enabled=True,
            url="https://synthetic-project.supabase.co",
            secret_key="supabase-secret-value",
        ),
    )


def ready_provider_result() -> ProviderReadiness:
    return ProviderReadiness(
        agent_count=2,
        expected_agents_match=True,
        agent_config_version_matches=True,
        provider_version_ids_present=True,
        provider_version_descriptions_match=True,
        prompt_dynamic_variables_match=True,
        data_collection_fields_match=True,
        provider_tools_omitted=True,
        intake_pre_call_enabled=True,
        workspace_pre_call_configured=True,
        post_call_events_configured=True,
        post_call_webhook_enabled=True,
        inbound_phone_assigned_to_intake=True,
        audio_saving_agent_count=2,
        short_retention_agent_count=2,
        concurrency_capacity=3,
        daily_call_capacity=8,
        provider_credits_available=True,
    )


def test_live_voice_preflight_check_only_is_safe_and_complete():
    settings = live_settings()
    provider = FakeProviderPreflightClient(ready_provider_result())
    supabase = FakeConnectivityClient(True)
    public_webhook = FakeConnectivityClient(True)

    report = run_preflight(
        settings,
        provider=provider,
        supabase=supabase,
        public_webhook=public_webhook,
        check_only=True,
    )
    safe = report.to_safe_dict()
    serialized = json.dumps(safe, sort_keys=True)

    assert report.ready is True
    assert safe["check_only"] is True
    assert safe["ready_for_supervised_three_call_run"] is True
    assert safe["counts"] == {
        "agents": 2,
        "audio_saving_agents": 2,
        "concurrency_capacity": 3,
        "daily_call_capacity": 8,
        "short_retention_agents": 2,
    }
    assert safe["checks"]["sequential_dispatch_required"] is False
    assert all(value.startswith("sha256:") for value in safe["identifiers"].values())
    for sensitive in (
        settings.live_voice.api_key,
        settings.live_voice.intake_agent_id,
        settings.live_voice.outbound_agent_id,
        settings.live_voice.phone_number_id,
        *settings.live_voice.destination_numbers,
        settings.live_voice.webhook_secret,
        settings.live_voice.precall_secret,
        settings.live_voice.recording_signing_secret,
        settings.live_voice.operator_secret,
        settings.supabase.secret_key,
    ):
        assert sensitive is not None
        assert sensitive not in serialized
    assert provider.calls == supabase.calls == public_webhook.calls == 1


def test_live_voice_preflight_fails_closed_without_network_when_config_is_invalid():
    settings = live_settings()
    settings = replace(
        settings,
        live_voice=replace(settings.live_voice, destination_numbers=()),
    )
    provider = FakeProviderPreflightClient(ready_provider_result())
    supabase = FakeConnectivityClient(True)
    public_webhook = FakeConnectivityClient(True)

    report = run_preflight(
        settings,
        provider=provider,
        supabase=supabase,
        public_webhook=public_webhook,
        check_only=True,
    )

    assert report.ready is False
    assert report.checks["configuration"] is False
    assert provider.calls == supabase.calls == public_webhook.calls == 0


def test_live_voice_preflight_allows_safe_sequential_dispatch_capacity():
    provider_result = replace(ready_provider_result(), concurrency_capacity=1)
    report = run_preflight(
        live_settings(),
        provider=FakeProviderPreflightClient(provider_result),
        supabase=FakeConnectivityClient(True),
        public_webhook=FakeConnectivityClient(True),
        check_only=True,
    )

    assert report.ready is True
    assert report.checks["concurrency_available"] is True
    assert report.checks["sequential_dispatch_required"] is True


def test_http_provider_preflight_reads_documented_provider_configuration(monkeypatch):
    settings = live_settings()
    intake_id = settings.live_voice.intake_agent_id
    outbound_id = settings.live_voice.outbound_agent_id
    phone_id = settings.live_voice.phone_number_id
    assert intake_id is not None
    assert outbound_id is not None
    assert phone_id is not None

    def prompt_with(variables):
        return " ".join(f"{{{{{name}}}}}" for name in variables)

    intake_version_id = "version-intake-opaque"
    outbound_version_id = "version-outbound-opaque"
    intake_branch_id = "branch-intake-opaque"
    outbound_branch_id = "branch-outbound-opaque"
    webhook_id = "webhook-opaque"
    base_url = settings.live_voice.api_base_url.rstrip("/")
    payloads = {
        f"{base_url}/v1/convai/agents/{intake_id}": {
            "agent_id": settings.live_voice.intake_agent_id,
            "name": "VeraMove Intake",
            "version_id": intake_version_id,
            "branch_id": intake_branch_id,
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": prompt_with(INTAKE_PROMPT_VARIABLES)
                    }
                }
            },
            "platform_settings": {
                "privacy": {"record_voice": True, "retention_days": 2},
                "call_limits": {"agent_concurrency_limit": 1, "daily_limit": 9},
                "overrides": {
                    "enable_conversation_initiation_client_data_from_webhook": True
                },
                "data_collection": {
                    name: {"type": "string"}
                    for name in INTAKE_DATA_COLLECTION_FIELDS
                },
            },
        },
        f"{base_url}/v1/convai/agents/{outbound_id}": {
            "agent_id": settings.live_voice.outbound_agent_id,
            "name": "VeraMove Outbound Negotiator",
            "version_id": outbound_version_id,
            "branch_id": outbound_branch_id,
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": prompt_with(OUTBOUND_PROMPT_VARIABLES)
                    }
                }
            },
            "platform_settings": {
                "privacy": {"record_voice": True, "retention_days": 2},
                "call_limits": {"agent_concurrency_limit": 1, "daily_limit": 8},
                "overrides": {
                    "enable_conversation_initiation_client_data_from_webhook": False
                },
                "data_collection": {
                    name: {"type": "string"}
                    for name in OUTBOUND_DATA_COLLECTION_FIELDS
                },
            },
        },
        (
            f"{base_url}/v1/convai/agents/{intake_id}/versions/{intake_version_id}"
        ): {
            "id": intake_version_id,
            "agent_id": intake_id,
            "branch_id": intake_branch_id,
            "version_description": "VeraMove 2026-07-21.2",
        },
        (
            f"{base_url}/v1/convai/agents/{outbound_id}/versions/{outbound_version_id}"
        ): {
            "id": outbound_version_id,
            "agent_id": outbound_id,
            "branch_id": outbound_branch_id,
            "version_description": "VeraMove 2026-07-21.2",
        },
        f"{base_url}/v1/convai/settings": {
            "conversation_initiation_client_data_webhook": {
                "url": "https://veramove.example.com/api/webhooks/elevenlabs/pre-call",
                "request_headers": {
                    "X-VeraMove-Precall-Secret": {"secret_id": "secret-opaque"}
                },
            },
            "webhooks": {
                "post_call_webhook_id": webhook_id,
                "events": ["transcript", "call_initiation_failure"],
                "transcript_format": "json",
                "send_audio": False,
            },
        },
        f"{base_url}/v1/workspace/webhooks": {
            "webhooks": [
                {
                    "webhook_id": webhook_id,
                    "webhook_url": "https://veramove.example.com/api/webhooks/elevenlabs",
                    "auth_type": "hmac",
                    "is_disabled": False,
                    "is_auto_disabled": False,
                }
            ]
        },
        f"{base_url}/v1/convai/phone-numbers/{phone_id}": {
            "phone_number_id": phone_id,
            "provider": "twilio",
            "assigned_agent": {"agent_id": intake_id},
        },
        f"{base_url}/v1/user/subscription": {
            "character_count": 100,
            "character_limit": 1_000,
        },
    }
    requests = []

    class Response:
        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self._body

    def fake_get(url, **kwargs):
        requests.append((url, kwargs.get("params")))
        return Response(payloads[url])

    monkeypatch.setattr("scripts.live_voice_preflight.httpx.get", fake_get)

    result = HttpElevenLabsPreflightClient().inspect(settings.live_voice)

    assert result == ProviderReadiness(
        agent_count=2,
        expected_agents_match=True,
        agent_config_version_matches=True,
        provider_version_ids_present=True,
        provider_version_descriptions_match=True,
        prompt_dynamic_variables_match=True,
        data_collection_fields_match=True,
        provider_tools_omitted=True,
        intake_pre_call_enabled=True,
        workspace_pre_call_configured=True,
        post_call_events_configured=True,
        post_call_webhook_enabled=True,
        inbound_phone_assigned_to_intake=True,
        audio_saving_agent_count=2,
        short_retention_agent_count=2,
        concurrency_capacity=1,
        daily_call_capacity=8,
        provider_credits_available=True,
    )
    assert requests == [
        (f"{base_url}/v1/convai/agents/{intake_id}", None),
        (f"{base_url}/v1/convai/agents/{outbound_id}", None),
        (
            f"{base_url}/v1/convai/agents/{intake_id}/versions/{intake_version_id}",
            None,
        ),
        (
            f"{base_url}/v1/convai/agents/{outbound_id}/versions/{outbound_version_id}",
            None,
        ),
        (f"{base_url}/v1/convai/settings", None),
        (f"{base_url}/v1/workspace/webhooks", {"include_usages": "true"}),
        (f"{base_url}/v1/convai/phone-numbers/{phone_id}", None),
        (f"{base_url}/v1/user/subscription", None),
    ]

    payloads[f"{base_url}/v1/convai/agents/{outbound_id}"]["platform_settings"]["privacy"][
        "retention_days"
    ] = 30
    assert (
        HttpElevenLabsPreflightClient().inspect(settings.live_voice).short_retention_agent_count
        == 1
    )

    payloads[f"{base_url}/v1/convai/settings"]["webhooks"]["events"] = ["transcript"]
    assert (
        HttpElevenLabsPreflightClient().inspect(settings.live_voice).post_call_events_configured
        is False
    )
    payloads[f"{base_url}/v1/convai/settings"][
        "conversation_initiation_client_data_webhook"
    ]["request_headers"]["X-VeraMove-Precall-Secret"] = "literal-secret-is-invalid"
    assert (
        HttpElevenLabsPreflightClient().inspect(settings.live_voice).workspace_pre_call_configured
        is False
    )
    payloads[f"{base_url}/v1/convai/phone-numbers/{phone_id}"]["assigned_agent"][
        "agent_id"
    ] = outbound_id
    assert (
        HttpElevenLabsPreflightClient()
        .inspect(settings.live_voice)
        .inbound_phone_assigned_to_intake
        is False
    )
    payloads[f"{base_url}/v1/convai/agents/{outbound_id}"]["conversation_config"]["agent"][
        "prompt"
    ]["tool_ids"] = ["unreviewed-provider-tool"]
    assert (
        HttpElevenLabsPreflightClient().inspect(settings.live_voice).provider_tools_omitted
        is False
    )


class FakeSmokeProvider:
    def __init__(self) -> None:
        self.calls = []

    def initiate_quote_call(
        self,
        job_spec,
        vendor,
        call_id,
        destination=None,
        call_plan=None,
    ):
        self.calls.append((job_spec, vendor, call_id, destination, call_plan))
        return VoiceCallResult(
            reference=VoiceCallReference(
                conversation_id="provider-conversation-secret",
                provider_call_id="provider-call-secret",
            )
        )


def _ready_preflight_report():
    return run_preflight(
        live_settings(),
        provider=FakeProviderPreflightClient(ready_provider_result()),
        supabase=FakeConnectivityClient(True),
        public_webhook=FakeConnectivityClient(True),
        check_only=True,
    )


def test_live_voice_smoke_requires_explicit_confirmation_and_never_calls_provider():
    provider = FakeSmokeProvider()

    with pytest.raises(ValueError, match="explicit confirmation"):
        run_supervised_smoke(
            live_settings(),
            provider=provider,
            preflight=_ready_preflight_report(),
            confirmed=False,
        )

    assert provider.calls == []


def test_live_voice_smoke_refuses_failed_preflight_and_uses_only_slot_zero():
    provider = FakeSmokeProvider()
    failed = run_preflight(
        live_settings(),
        provider=FakeProviderPreflightClient(
            replace(ready_provider_result(), provider_credits_available=False)
        ),
        supabase=FakeConnectivityClient(True),
        public_webhook=FakeConnectivityClient(True),
        check_only=True,
    )
    with pytest.raises(ValueError, match="preflight"):
        run_supervised_smoke(
            live_settings(),
            provider=provider,
            preflight=failed,
            confirmed=True,
        )
    assert provider.calls == []

    result = run_supervised_smoke(
        live_settings(),
        provider=provider,
        preflight=_ready_preflight_report(),
        confirmed=True,
    )

    assert result == {
        "correlation": "sha256:6cc9b1298c8f",
        "destination_slots_used": 1,
        "preflight_ready": True,
        "provider_reference_received": True,
    }
    assert len(provider.calls) == 1
    job_spec, vendor, call_id, destination, call_plan = provider.calls[0]
    assert job_spec.confirmed is True
    assert job_spec.locked_version == job_spec.version
    assert job_spec.data_classification == "role_play"
    assert vendor.data_classification == "role_play"
    assert call_id == UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
    assert destination.destination_slot == 0
    assert call_plan is None
    assert "provider-conversation-secret" not in json.dumps(result)
    assert "provider-call-secret" not in json.dumps(result)


def test_live_voice_smoke_rejects_preflight_from_another_configuration():
    provider = FakeSmokeProvider()
    preflight = _ready_preflight_report()
    stale_identifiers = dict(preflight.identifiers)
    stale_identifiers["outbound_agent"] = "sha256:stale0000000"

    with pytest.raises(ValueError, match="current configuration"):
        run_supervised_smoke(
            live_settings(),
            provider=provider,
            preflight=replace(preflight, identifiers=stale_identifiers),
            confirmed=True,
        )

    assert provider.calls == []
