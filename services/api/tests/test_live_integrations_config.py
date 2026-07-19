"""Fail-closed configuration tests for optional live integrations."""

import pytest

from services.api.app.core.config import (
    LiveVoiceConfig,
    OpenAIConfig,
    Settings,
    SupabaseConfig,
    TavilyConfig,
)
from services.api.app.core.errors import ProviderConfigurationError

INTEGRATION_ENV_NAMES = (
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
    "PUBLIC_API_BASE_URL",
    "RECORDING_SIGNING_SECRET",
    "VOICE_OPERATOR_SECRET",
    "AGENT_CONFIG_VERSION",
    "OPENAI_ENABLED",
    "OPENAI_API_KEY",
    "OPENAI_DOCUMENT_MODEL",
    "OPENAI_RECOMMENDATION_MODEL",
    "OPENAI_API_BASE_URL",
    "TAVILY_ENABLED",
    "TAVILY_API_KEY",
    "TAVILY_API_BASE_URL",
    "SUPABASE_ENABLED",
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
)

LONG_SECRET = "s" * 32
DESTINATIONS = ("+15550100001", "+15550100002", "+15550100003")


def clear_integration_env(monkeypatch) -> None:
    for name in INTEGRATION_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def complete_live_voice_config(**updates: object) -> LiveVoiceConfig:
    values: dict[str, object] = {
        "api_key": "synthetic-elevenlabs-key",
        "intake_agent_id": "synthetic-intake-agent",
        "outbound_agent_id": "synthetic-outbound-agent",
        "phone_number_id": "synthetic-phone-number-id",
        "destination_numbers": DESTINATIONS,
        "webhook_secret": LONG_SECRET,
        "precall_secret": "p" * 32,
        "recording_signing_secret": "r" * 32,
        "operator_secret": "o" * 32,
        "public_api_base_url": "https://api.veramove.example",
        "agent_config_version": "2026-07-19.v1",
        "live_calls_enabled": True,
    }
    values.update(updates)
    return LiveVoiceConfig(**values)


def complete_live_settings(**voice_updates: object) -> Settings:
    return Settings(
        app_mode="live",
        live_voice=complete_live_voice_config(**voice_updates),
        supabase=SupabaseConfig(
            enabled=True,
            url="https://synthetic-project.supabase.co",
            secret_key="synthetic-supabase-secret",
        ),
    )


def set_complete_live_env(monkeypatch) -> None:
    clear_integration_env(monkeypatch)
    values = {
        "APP_MODE": "live",
        "LIVE_CALLS_ENABLED": "true",
        "ELEVENLABS_API_KEY": "synthetic-elevenlabs-key",
        "ELEVENLABS_INTAKE_AGENT_ID": "synthetic-intake-agent",
        "ELEVENLABS_OUTBOUND_AGENT_ID": "synthetic-outbound-agent",
        "ELEVENLABS_PHONE_NUMBER_ID": "synthetic-phone-number-id",
        "ELEVENLABS_WEBHOOK_SECRET": LONG_SECRET,
        "ELEVENLABS_PRECALL_SECRET": "p" * 32,
        "LIVE_TEST_TO_NUMBERS": ",".join(DESTINATIONS),
        "PUBLIC_API_BASE_URL": "https://api.veramove.example/",
        "RECORDING_SIGNING_SECRET": "r" * 32,
        "VOICE_OPERATOR_SECRET": "o" * 32,
        "AGENT_CONFIG_VERSION": "2026-07-19.v1",
        "SUPABASE_ENABLED": "true",
        "SUPABASE_URL": "https://synthetic-project.supabase.co",
        "SUPABASE_SECRET_KEY": "synthetic-supabase-secret",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_live_voice_parses_two_agents_and_exactly_three_destinations(monkeypatch):
    set_complete_live_env(monkeypatch)

    config = Settings.from_env().require_live_voice_config()

    assert config.intake_agent_id == "synthetic-intake-agent"
    assert config.outbound_agent_id == "synthetic-outbound-agent"
    assert config.destination_numbers == DESTINATIONS
    assert config.public_api_base_url == "https://api.veramove.example"
    assert config.agent_config_version == "2026-07-19.v1"


@pytest.mark.parametrize("missing_field", ("intake_agent_id", "outbound_agent_id"))
def test_live_voice_requires_both_role_agent_ids(missing_field):
    settings = complete_live_settings(**{missing_field: None})

    with pytest.raises(ProviderConfigurationError, match="AGENT_ID"):
        settings.require_live_voice_config()


def test_equal_legacy_outbound_agent_aliases_are_accepted(monkeypatch):
    set_complete_live_env(monkeypatch)
    monkeypatch.delenv("ELEVENLABS_OUTBOUND_AGENT_ID")
    monkeypatch.setenv("ELEVENLABS_QUOTE_AGENT_ID", "synthetic-outbound-agent")
    monkeypatch.setenv("ELEVENLABS_NEGOTIATOR_AGENT_ID", "synthetic-outbound-agent")

    assert (
        Settings.from_env().require_live_voice_config().outbound_agent_id
        == "synthetic-outbound-agent"
    )


@pytest.mark.parametrize(
    ("quote_id", "negotiator_id", "preferred_id"),
    [
        ("quote-agent", "negotiator-agent", None),
        ("legacy-agent", None, None),
        (None, "legacy-agent", None),
        ("legacy-agent", "legacy-agent", "preferred-agent"),
    ],
)
def test_ambiguous_legacy_outbound_agent_aliases_fail_closed(
    monkeypatch,
    quote_id,
    negotiator_id,
    preferred_id,
):
    clear_integration_env(monkeypatch)
    for name, value in {
        "ELEVENLABS_QUOTE_AGENT_ID": quote_id,
        "ELEVENLABS_NEGOTIATOR_AGENT_ID": negotiator_id,
        "ELEVENLABS_OUTBOUND_AGENT_ID": preferred_id,
    }.items():
        if value is not None:
            monkeypatch.setenv(name, value)

    with pytest.raises(ProviderConfigurationError, match="outbound agent"):
        Settings.from_env()


@pytest.mark.parametrize(
    "value",
    [
        "+15550100001",
        "+15550100001,+15550100002,+15550100003,+15550100004",
        "+15550100001,+15550100001,+15550100003",
        "+15550100001,5550100002,+15550100003",
        "+05550100001,+15550100002,+15550100003",
    ],
)
def test_live_destinations_require_exactly_three_unique_e164_values(
    monkeypatch,
    value,
):
    clear_integration_env(monkeypatch)
    monkeypatch.setenv("LIVE_TEST_TO_NUMBERS", value)

    with pytest.raises(ProviderConfigurationError, match="LIVE_TEST_TO_NUMBERS"):
        Settings.from_env()


def test_live_destinations_are_trimmed(monkeypatch):
    set_complete_live_env(monkeypatch)
    monkeypatch.setenv(
        "LIVE_TEST_TO_NUMBERS",
        " +15550100001, +15550100002 ,+15550100003 ",
    )

    assert Settings.from_env().live_voice.destination_numbers == DESTINATIONS


def test_full_live_voice_rejects_missing_destinations():
    settings = complete_live_settings(destination_numbers=())

    with pytest.raises(ProviderConfigurationError, match="LIVE_TEST_TO_NUMBERS"):
        settings.require_live_voice_config()


def test_public_api_base_url_must_be_https_origin(monkeypatch):
    clear_integration_env(monkeypatch)
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "http://api.veramove.example")

    with pytest.raises(ProviderConfigurationError, match="HTTPS origin"):
        Settings.from_env()


@pytest.mark.parametrize(
    ("field", "environment_name"),
    [
        ("webhook_secret", "ELEVENLABS_WEBHOOK_SECRET"),
        ("precall_secret", "ELEVENLABS_PRECALL_SECRET"),
        ("recording_signing_secret", "RECORDING_SIGNING_SECRET"),
        ("operator_secret", "VOICE_OPERATOR_SECRET"),
    ],
)
@pytest.mark.parametrize("value", (None, "too-short"))
def test_live_voice_requires_strong_runtime_secrets(field, environment_name, value):
    settings = complete_live_settings(**{field: value})

    with pytest.raises(ProviderConfigurationError, match=environment_name):
        settings.require_live_voice_config()


def test_live_voice_requires_durable_supabase():
    settings = Settings(
        app_mode="live",
        live_voice=complete_live_voice_config(),
    )

    with pytest.raises(ProviderConfigurationError, match="SUPABASE_ENABLED=true"):
        settings.require_live_voice_config()


def test_live_shaped_values_do_not_activate_voice_in_mock_mode(monkeypatch):
    set_complete_live_env(monkeypatch)
    monkeypatch.setenv("APP_MODE", "mock")

    settings = Settings.from_env()

    assert settings.live_voice.destination_numbers == DESTINATIONS
    with pytest.raises(ProviderConfigurationError, match="APP_MODE=live"):
        settings.require_live_voice_config()


def test_live_integrations_default_disabled(monkeypatch):
    clear_integration_env(monkeypatch)

    settings = Settings.from_env()

    assert settings.live_voice == LiveVoiceConfig()
    assert settings.openai == OpenAIConfig()
    assert settings.tavily == TavilyConfig()
    assert settings.supabase == SupabaseConfig()


def test_live_integrations_parse_complete_configuration(monkeypatch):
    clear_integration_env(monkeypatch)
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai-secret")
    monkeypatch.setenv("OPENAI_DOCUMENT_MODEL", "synthetic-document-model")
    monkeypatch.setenv("OPENAI_RECOMMENDATION_MODEL", "synthetic-narrator-model")
    monkeypatch.setenv("OPENAI_API_BASE_URL", "https://openai.example")
    monkeypatch.setenv("TAVILY_ENABLED", "yes")
    monkeypatch.setenv("TAVILY_API_KEY", "synthetic-tavily-secret")
    monkeypatch.setenv("TAVILY_API_BASE_URL", "https://tavily.example")
    monkeypatch.setenv("SUPABASE_ENABLED", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "synthetic-supabase-secret")

    settings = Settings.from_env()

    assert settings.require_openai_config() == OpenAIConfig(
        enabled=True,
        api_key="synthetic-openai-secret",
        document_model="synthetic-document-model",
        recommendation_model="synthetic-narrator-model",
        api_base_url="https://openai.example",
    )
    assert settings.require_tavily_config() == TavilyConfig(
        enabled=True,
        api_key="synthetic-tavily-secret",
        api_base_url="https://tavily.example",
    )
    assert settings.require_supabase_config() == SupabaseConfig(
        enabled=True,
        url="https://synthetic-project.supabase.co",
        secret_key="synthetic-supabase-secret",
    )


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        (Settings(openai=OpenAIConfig(enabled=True)), "OPENAI_API_KEY"),
        (Settings(tavily=TavilyConfig(enabled=True)), "TAVILY_API_KEY"),
        (Settings(supabase=SupabaseConfig(enabled=True)), "SUPABASE_URL"),
        (
            Settings(
                supabase=SupabaseConfig(
                    enabled=True,
                    url="https://synthetic-project.supabase.co",
                )
            ),
            "SUPABASE_SECRET_KEY",
        ),
    ],
)
def test_enabled_integrations_require_complete_configuration(settings, message):
    require = {
        "OPENAI_API_KEY": settings.require_openai_config,
        "TAVILY_API_KEY": settings.require_tavily_config,
        "SUPABASE_URL": settings.require_supabase_config,
        "SUPABASE_SECRET_KEY": settings.require_supabase_config,
    }[message]

    with pytest.raises(ProviderConfigurationError, match=message):
        require()


def test_disabled_integration_requirement_fails_closed():
    with pytest.raises(ProviderConfigurationError, match="OPENAI_ENABLED=true"):
        Settings().require_openai_config()
    with pytest.raises(ProviderConfigurationError, match="TAVILY_ENABLED=true"):
        Settings().require_tavily_config()
    with pytest.raises(ProviderConfigurationError, match="SUPABASE_ENABLED=true"):
        Settings().require_supabase_config()


def test_supabase_secret_key_precedes_legacy_service_role(monkeypatch):
    clear_integration_env(monkeypatch)
    monkeypatch.setenv("SUPABASE_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "synthetic-new-secret")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-legacy-secret")

    assert Settings.from_env().require_supabase_config().secret_key == "synthetic-new-secret"


def test_supabase_accepts_legacy_service_role_fallback(monkeypatch):
    clear_integration_env(monkeypatch)
    monkeypatch.setenv("SUPABASE_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-legacy-secret")

    assert Settings.from_env().require_supabase_config().secret_key == "synthetic-legacy-secret"


@pytest.mark.parametrize(
    "name",
    ("OPENAI_API_BASE_URL", "TAVILY_API_BASE_URL", "SUPABASE_URL"),
)
@pytest.mark.parametrize(
    "value",
    (
        "http://provider.example",
        "https://provider.example/path",
        "https://provider.example?secret=unsafe",
        "https://user:password@provider.example",
    ),
)
def test_provider_base_url_requires_https_origin(monkeypatch, name, value):
    clear_integration_env(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ProviderConfigurationError, match="HTTPS origin"):
        Settings.from_env()


def test_configuration_error_never_contains_secret_value():
    secret = "synthetic-must-not-appear"
    settings = Settings(
        supabase=SupabaseConfig(
            enabled=True,
            url=None,
            secret_key=secret,
        )
    )

    with pytest.raises(ProviderConfigurationError) as exc_info:
        settings.require_supabase_config()

    assert secret not in str(exc_info.value)
