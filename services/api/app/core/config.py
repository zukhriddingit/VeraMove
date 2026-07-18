"""Environment-backed settings with safe mock defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from services.api.app.core.errors import ProviderConfigurationError

TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_ENV_VALUES = frozenset({"0", "false", "no", "off"})


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _boolean_env(name: str, *, default: bool = False) -> bool:
    value = _optional_env(name)
    if value is None:
        return default
    normalized = value.lower()
    if normalized in TRUE_ENV_VALUES:
        return True
    if normalized in FALSE_ENV_VALUES:
        return False
    raise ProviderConfigurationError(
        f"{name} must be one of: 1, true, yes, on, 0, false, no, off"
    )


@dataclass(frozen=True, slots=True)
class LiveVoiceConfig:
    """Secrets and identifiers required only when a live call is initiated."""

    api_key: str | None = None
    quote_agent_id: str | None = None
    negotiator_agent_id: str | None = None
    phone_number_id: str | None = None
    test_to_number: str | None = None
    webhook_secret: str | None = None
    live_calls_enabled: bool = False
    api_base_url: str = "https://api.elevenlabs.io"


@dataclass(frozen=True, slots=True)
class Settings:
    app_mode: str = "mock"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    live_voice: LiveVoiceConfig = field(default_factory=LiveVoiceConfig)

    def require_live_voice_config(self) -> LiveVoiceConfig:
        """Fail closed unless every controlled-live-call guard is present."""

        if self.app_mode != "live":
            raise ProviderConfigurationError("Live voice requires APP_MODE=live")
        config = self.live_voice
        if not config.live_calls_enabled:
            raise ProviderConfigurationError(
                "Live calls require LIVE_CALLS_ENABLED=true"
            )
        required = {
            "ELEVENLABS_API_KEY": config.api_key,
            "ELEVENLABS_QUOTE_AGENT_ID": config.quote_agent_id,
            "ELEVENLABS_NEGOTIATOR_AGENT_ID": config.negotiator_agent_id,
            "ELEVENLABS_PHONE_NUMBER_ID": config.phone_number_id,
            "ELEVENLABS_WEBHOOK_SECRET": config.webhook_secret,
            "LIVE_TEST_TO_NUMBER": config.test_to_number,
        }
        missing = [
            name
            for name, value in required.items()
            if value is None or not value.strip()
        ]
        if missing:
            raise ProviderConfigurationError(
                f"Missing live voice configuration: {', '.join(missing)}"
            )
        return config

    @classmethod
    def from_env(cls) -> Settings:
        app_mode = os.getenv("APP_MODE", "mock").strip().lower()
        if app_mode not in {"mock", "live"}:
            raise ProviderConfigurationError("APP_MODE must be either mock or live")
        return cls(
            app_mode=app_mode,
            api_host=os.getenv("API_HOST", "127.0.0.1").strip(),
            api_port=int(os.getenv("API_PORT", "8000")),
            live_voice=LiveVoiceConfig(
                api_key=_optional_env("ELEVENLABS_API_KEY"),
                quote_agent_id=_optional_env("ELEVENLABS_QUOTE_AGENT_ID"),
                negotiator_agent_id=_optional_env(
                    "ELEVENLABS_NEGOTIATOR_AGENT_ID"
                ),
                phone_number_id=_optional_env("ELEVENLABS_PHONE_NUMBER_ID"),
                test_to_number=_optional_env("LIVE_TEST_TO_NUMBER"),
                webhook_secret=_optional_env("ELEVENLABS_WEBHOOK_SECRET"),
                live_calls_enabled=_boolean_env("LIVE_CALLS_ENABLED"),
                api_base_url=(
                    _optional_env("ELEVENLABS_API_BASE_URL")
                    or "https://api.elevenlabs.io"
                ),
            ),
        )
