"""Fail-closed configuration tests for optional live integrations."""

import pytest

from services.api.app.core.config import (
    OpenAIConfig,
    Settings,
    SupabaseConfig,
    TavilyConfig,
)
from services.api.app.core.errors import ProviderConfigurationError

INTEGRATION_ENV_NAMES = (
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


def clear_integration_env(monkeypatch) -> None:
    for name in INTEGRATION_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_live_integrations_default_disabled(monkeypatch):
    clear_integration_env(monkeypatch)

    settings = Settings.from_env()

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

    assert (
        Settings.from_env().require_supabase_config().secret_key
        == "synthetic-new-secret"
    )


def test_supabase_accepts_legacy_service_role_fallback(monkeypatch):
    clear_integration_env(monkeypatch)
    monkeypatch.setenv("SUPABASE_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-legacy-secret")

    assert (
        Settings.from_env().require_supabase_config().secret_key
        == "synthetic-legacy-secret"
    )


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
