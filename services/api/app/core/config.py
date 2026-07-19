"""Environment-backed settings with safe mock defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from services.api.app.core.errors import ProviderConfigurationError

TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_ENV_VALUES = frozenset({"0", "false", "no", "off"})
DEFAULT_CORS_ALLOW_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


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


def _cors_origins_env() -> tuple[str, ...]:
    value = _optional_env("CORS_ALLOW_ORIGINS")
    if value is None:
        return DEFAULT_CORS_ALLOW_ORIGINS
    origins = tuple(
        dict.fromkeys(
            item.strip().rstrip("/")
            for item in value.split(",")
            if item.strip()
        )
    )
    if not origins or "*" in origins:
        raise ProviderConfigurationError(
            "CORS_ALLOW_ORIGINS must contain explicit HTTP(S) origins"
        )
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderConfigurationError(
                "CORS_ALLOW_ORIGINS must contain explicit HTTP(S) origins"
            )
    return origins


def _https_origin(name: str, value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ProviderConfigurationError(f"{name} must be an HTTPS origin")
    return normalized


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
class OpenAIConfig:
    """Optional structured extraction and grounded narration settings."""

    enabled: bool = False
    api_key: str | None = None
    document_model: str = "gpt-5.6-luna"
    recommendation_model: str = "gpt-5.6-terra"
    api_base_url: str = "https://api.openai.com"


@dataclass(frozen=True, slots=True)
class TavilyConfig:
    """Optional search-backed vendor discovery settings."""

    enabled: bool = False
    api_key: str | None = None
    api_base_url: str = "https://api.tavily.com"


@dataclass(frozen=True, slots=True)
class SupabaseConfig:
    """Optional server-side persistent repository settings."""

    enabled: bool = False
    url: str | None = None
    secret_key: str | None = None


@dataclass(frozen=True, slots=True)
class Settings:
    app_mode: str = "mock"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_allow_origins: tuple[str, ...] = DEFAULT_CORS_ALLOW_ORIGINS
    live_voice: LiveVoiceConfig = field(default_factory=LiveVoiceConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    tavily: TavilyConfig = field(default_factory=TavilyConfig)
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)

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

    def require_openai_config(self) -> OpenAIConfig:
        """Fail closed unless the optional OpenAI boundary is fully enabled."""

        config = self.openai
        if not config.enabled:
            raise ProviderConfigurationError(
                "OpenAI integration requires OPENAI_ENABLED=true"
            )
        missing = [
            name
            for name, value in {
                "OPENAI_API_KEY": config.api_key,
                "OPENAI_DOCUMENT_MODEL": config.document_model,
                "OPENAI_RECOMMENDATION_MODEL": config.recommendation_model,
            }.items()
            if value is None or not value.strip()
        ]
        if missing:
            raise ProviderConfigurationError(
                f"Missing OpenAI configuration: {', '.join(missing)}"
            )
        return config

    def require_tavily_config(self) -> TavilyConfig:
        """Fail closed unless the optional Tavily boundary is fully enabled."""

        config = self.tavily
        if not config.enabled:
            raise ProviderConfigurationError(
                "Tavily integration requires TAVILY_ENABLED=true"
            )
        if config.api_key is None or not config.api_key.strip():
            raise ProviderConfigurationError(
                "Missing Tavily configuration: TAVILY_API_KEY"
            )
        return config

    def require_supabase_config(self) -> SupabaseConfig:
        """Fail closed unless the persistent repository is fully enabled."""

        config = self.supabase
        if not config.enabled:
            raise ProviderConfigurationError(
                "Supabase integration requires SUPABASE_ENABLED=true"
            )
        missing = [
            name
            for name, value in {
                "SUPABASE_URL": config.url,
                "SUPABASE_SECRET_KEY": config.secret_key,
            }.items()
            if value is None or not value.strip()
        ]
        if missing:
            raise ProviderConfigurationError(
                f"Missing Supabase configuration: {', '.join(missing)}"
            )
        return config

    @classmethod
    def from_env(cls) -> Settings:
        app_mode = os.getenv("APP_MODE", "mock").strip().lower()
        if app_mode not in {"mock", "live"}:
            raise ProviderConfigurationError("APP_MODE must be either mock or live")
        supabase_url = _optional_env("SUPABASE_URL")
        return cls(
            app_mode=app_mode,
            api_host=os.getenv("API_HOST", "127.0.0.1").strip(),
            api_port=int(os.getenv("API_PORT", "8000")),
            cors_allow_origins=_cors_origins_env(),
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
            openai=OpenAIConfig(
                enabled=_boolean_env("OPENAI_ENABLED"),
                api_key=_optional_env("OPENAI_API_KEY"),
                document_model=(
                    _optional_env("OPENAI_DOCUMENT_MODEL") or "gpt-5.6-luna"
                ),
                recommendation_model=(
                    _optional_env("OPENAI_RECOMMENDATION_MODEL")
                    or "gpt-5.6-terra"
                ),
                api_base_url=_https_origin(
                    "OPENAI_API_BASE_URL",
                    _optional_env("OPENAI_API_BASE_URL")
                    or "https://api.openai.com",
                ),
            ),
            tavily=TavilyConfig(
                enabled=_boolean_env("TAVILY_ENABLED"),
                api_key=_optional_env("TAVILY_API_KEY"),
                api_base_url=_https_origin(
                    "TAVILY_API_BASE_URL",
                    _optional_env("TAVILY_API_BASE_URL")
                    or "https://api.tavily.com",
                ),
            ),
            supabase=SupabaseConfig(
                enabled=_boolean_env("SUPABASE_ENABLED"),
                url=(
                    _https_origin("SUPABASE_URL", supabase_url)
                    if supabase_url is not None
                    else None
                ),
                secret_key=(
                    _optional_env("SUPABASE_SECRET_KEY")
                    or _optional_env("SUPABASE_SERVICE_ROLE_KEY")
                ),
            ),
        )
