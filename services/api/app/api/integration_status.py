"""Provider-neutral, read-only integration status with safe OpenAI aggregates."""

from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from services.api.app.core.config import (
    E164_PATTERN,
    MIN_LIVE_SECRET_BYTES,
    Settings,
)
from services.api.app.observability.usage import UsageAggregate, UsageRecorder


class ProviderIntegrationStatus(BaseModel):
    """Boolean-only state that cannot reveal provider configuration values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    configured: bool


class OpenAIIntegrationStatus(ProviderIntegrationStatus):
    """OpenAI state plus grouped, content-free usage measurements."""

    usage: tuple[UsageAggregate, ...] = ()


class IntegrationStatusSnapshot(BaseModel):
    """Safe public status shape for all independently configured integrations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    openai: OpenAIIntegrationStatus
    tavily: ProviderIntegrationStatus
    supabase: ProviderIntegrationStatus
    live_voice: ProviderIntegrationStatus


class IntegrationStatusReporter:
    """Bind one settings snapshot and one app-scoped recorder."""

    def __init__(self, settings: Settings, usage_recorder: UsageRecorder) -> None:
        self._settings = settings
        self._usage_recorder = usage_recorder

    @property
    def usage_recorder(self) -> UsageRecorder:
        return self._usage_recorder

    def snapshot(self) -> IntegrationStatusSnapshot:
        """Build a safe snapshot from this application's immutable settings."""

        openai = self._settings.openai
        tavily = self._settings.tavily
        supabase = self._settings.supabase
        voice = self._settings.live_voice
        return IntegrationStatusSnapshot(
            openai=OpenAIIntegrationStatus(
                enabled=openai.enabled,
                configured=all(
                    _present(value)
                    for value in (
                        openai.api_key,
                        openai.document_model,
                        openai.recommendation_model,
                    )
                ),
                usage=self._usage_recorder.aggregates(),
            ),
            tavily=ProviderIntegrationStatus(
                enabled=tavily.enabled,
                configured=_present(tavily.api_key),
            ),
            supabase=ProviderIntegrationStatus(
                enabled=supabase.enabled,
                configured=_present(supabase.url) and _present(supabase.secret_key),
            ),
            live_voice=ProviderIntegrationStatus(
                enabled=self._settings.app_mode == "live" and voice.live_calls_enabled,
                configured=_live_voice_configured(self._settings),
            ),
        )


def _present(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _strong_secret(value: str | None) -> bool:
    return _present(value) and len(value.encode("utf-8")) >= MIN_LIVE_SECRET_BYTES


def _https_origin(value: str | None) -> bool:
    if not _present(value):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
        and parsed.username is None
        and parsed.password is None
    )


def _live_voice_configured(settings: Settings) -> bool:
    config = settings.live_voice
    destinations_valid = (
        len(config.destination_numbers) == 3
        and len(set(config.destination_numbers)) == 3
        and all(E164_PATTERN.fullmatch(number) for number in config.destination_numbers)
    )
    agents_distinct = (
        _present(config.intake_agent_id)
        and _present(config.outbound_agent_id)
        and config.intake_agent_id != config.outbound_agent_id
    )
    return (
        all(
            _present(value)
            for value in (
                config.api_key,
                config.intake_agent_id,
                config.outbound_agent_id,
                config.phone_number_id,
                config.agent_config_version,
            )
        )
        and agents_distinct
        and destinations_valid
        and _https_origin(config.public_api_base_url)
        and all(
            _strong_secret(value)
            for value in (
                config.webhook_secret,
                config.precall_secret,
                config.recording_signing_secret,
                config.operator_secret,
            )
        )
        and _present(settings.supabase.url)
        and _present(settings.supabase.secret_key)
    )


__all__ = [
    "IntegrationStatusReporter",
    "IntegrationStatusSnapshot",
    "OpenAIIntegrationStatus",
    "ProviderIntegrationStatus",
]
