"""Environment-backed settings with safe mock defaults."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from services.api.app.core.errors import ProviderConfigurationError

TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_ENV_VALUES = frozenset({"0", "false", "no", "off"})
DEFAULT_CORS_ALLOW_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)
E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
MIN_LIVE_SECRET_BYTES = 32


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
    raise ProviderConfigurationError(f"{name} must be one of: 1, true, yes, on, 0, false, no, off")


def _bounded_integer_env(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = _optional_env(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ProviderConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ProviderConfigurationError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


def _cors_origins_env() -> tuple[str, ...]:
    value = _optional_env("CORS_ALLOW_ORIGINS")
    if value is None:
        return DEFAULT_CORS_ALLOW_ORIGINS
    origins = tuple(
        dict.fromkeys(item.strip().rstrip("/") for item in value.split(",") if item.strip())
    )
    if not origins or "*" in origins:
        raise ProviderConfigurationError("CORS_ALLOW_ORIGINS must contain explicit HTTP(S) origins")
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


def _outbound_agent_id_env() -> str | None:
    """Resolve the one outbound role without accepting ambiguous old aliases."""

    preferred = _optional_env("ELEVENLABS_OUTBOUND_AGENT_ID")
    legacy_quote = _optional_env("ELEVENLABS_QUOTE_AGENT_ID")
    legacy_negotiator = _optional_env("ELEVENLABS_NEGOTIATOR_AGENT_ID")
    legacy_present = legacy_quote is not None or legacy_negotiator is not None
    if legacy_present and (
        legacy_quote is None or legacy_negotiator is None or legacy_quote != legacy_negotiator
    ):
        raise ProviderConfigurationError(
            "Legacy outbound agent aliases must both exist and identify one outbound agent"
        )
    if preferred is not None and legacy_quote is not None and preferred != legacy_quote:
        raise ProviderConfigurationError(
            "Preferred and legacy settings must identify one outbound agent"
        )
    return preferred or legacy_quote


def _destination_numbers_env() -> tuple[str, ...]:
    value = _optional_env("LIVE_TEST_TO_NUMBERS")
    if value is None:
        return ()
    numbers = tuple(item.strip() for item in value.split(",") if item.strip())
    if (
        len(numbers) != 3
        or len(set(numbers)) != 3
        or any(E164_PATTERN.fullmatch(number) is None for number in numbers)
    ):
        raise ProviderConfigurationError(
            "LIVE_TEST_TO_NUMBERS must contain exactly three unique E.164 numbers"
        )
    return numbers


def _secret_is_strong(value: str | None) -> bool:
    return value is not None and len(value.encode("utf-8")) >= MIN_LIVE_SECRET_BYTES


@dataclass(frozen=True, slots=True)
class LiveVoiceConfig:
    """Secrets and identifiers required only when a live call is initiated."""

    api_key: str | None = None
    intake_agent_id: str | None = None
    outbound_agent_id: str | None = None
    phone_number_id: str | None = None
    destination_numbers: tuple[str, ...] = ()
    webhook_secret: str | None = None
    precall_secret: str | None = None
    recording_signing_secret: str | None = None
    operator_secret: str | None = None
    public_api_base_url: str | None = None
    agent_config_version: str | None = None
    live_calls_enabled: bool = False
    real_vendor_calls_enabled: bool = False
    contact_hash_secret: str | None = None
    vendor_consent_max_age_days: int = 30
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
            raise ProviderConfigurationError("Live calls require LIVE_CALLS_ENABLED=true")
        if not self.supabase.enabled:
            raise ProviderConfigurationError("Live voice requires SUPABASE_ENABLED=true")
        self.require_supabase_config()
        required = {
            "ELEVENLABS_API_KEY": config.api_key,
            "ELEVENLABS_INTAKE_AGENT_ID": config.intake_agent_id,
            "ELEVENLABS_OUTBOUND_AGENT_ID": config.outbound_agent_id,
            "ELEVENLABS_PHONE_NUMBER_ID": config.phone_number_id,
            "PUBLIC_API_BASE_URL": config.public_api_base_url,
            "AGENT_CONFIG_VERSION": config.agent_config_version,
        }
        missing = [name for name, value in required.items() if value is None or not value.strip()]
        if missing:
            raise ProviderConfigurationError(
                f"Missing live voice configuration: {', '.join(missing)}"
            )
        if (
            len(config.destination_numbers) != 3
            or len(set(config.destination_numbers)) != 3
            or any(E164_PATTERN.fullmatch(number) is None for number in config.destination_numbers)
        ):
            raise ProviderConfigurationError(
                "LIVE_TEST_TO_NUMBERS must contain exactly three unique E.164 numbers"
            )
        secrets = {
            "ELEVENLABS_WEBHOOK_SECRET": config.webhook_secret,
            "ELEVENLABS_PRECALL_SECRET": config.precall_secret,
            "RECORDING_SIGNING_SECRET": config.recording_signing_secret,
            "VOICE_OPERATOR_SECRET": config.operator_secret,
        }
        weak = [name for name, value in secrets.items() if not _secret_is_strong(value)]
        if weak:
            raise ProviderConfigurationError(
                "Live voice secrets must be at least "
                f"{MIN_LIVE_SECRET_BYTES} bytes: {', '.join(weak)}"
            )
        assert config.public_api_base_url is not None
        _https_origin("PUBLIC_API_BASE_URL", config.public_api_base_url)
        return config

    def require_browser_voice_config(self) -> LiveVoiceConfig:
        """Require only the live settings needed for authenticated browser intake."""

        if self.app_mode != "live":
            raise ProviderConfigurationError("Browser voice requires APP_MODE=live")
        config = self.live_voice
        if not config.live_calls_enabled:
            raise ProviderConfigurationError(
                "Browser voice requires LIVE_CALLS_ENABLED=true"
            )
        self.require_supabase_config()
        required = {
            "ELEVENLABS_API_KEY": config.api_key,
            "ELEVENLABS_INTAKE_AGENT_ID": config.intake_agent_id,
            "AGENT_CONFIG_VERSION": config.agent_config_version,
        }
        missing = [
            name for name, value in required.items() if value is None or not value.strip()
        ]
        if missing:
            raise ProviderConfigurationError(
                f"Missing browser voice configuration: {', '.join(missing)}"
            )
        if not _secret_is_strong(config.webhook_secret):
            raise ProviderConfigurationError(
                "ELEVENLABS_WEBHOOK_SECRET must be at least "
                f"{MIN_LIVE_SECRET_BYTES} bytes"
            )
        return config

    def require_real_vendor_call_config(self) -> LiveVoiceConfig:
        """Fail closed for consented official-business calls without test destinations."""

        if self.app_mode != "live":
            raise ProviderConfigurationError(
                "Real vendor calls require APP_MODE=live"
            )
        config = self.live_voice
        if not config.live_calls_enabled or not config.real_vendor_calls_enabled:
            raise ProviderConfigurationError(
                "Real vendor calls require LIVE_CALLS_ENABLED=true and "
                "REAL_VENDOR_CALLS_ENABLED=true"
            )
        self.require_supabase_config()
        required = {
            "ELEVENLABS_API_KEY": config.api_key,
            "ELEVENLABS_OUTBOUND_AGENT_ID": config.outbound_agent_id,
            "ELEVENLABS_PHONE_NUMBER_ID": config.phone_number_id,
            "PUBLIC_API_BASE_URL": config.public_api_base_url,
            "AGENT_CONFIG_VERSION": config.agent_config_version,
        }
        missing = [
            name
            for name, value in required.items()
            if value is None or not value.strip()
        ]
        if missing:
            raise ProviderConfigurationError(
                f"Missing real vendor call configuration: {', '.join(missing)}"
            )
        secrets = {
            "ELEVENLABS_WEBHOOK_SECRET": config.webhook_secret,
            "RECORDING_SIGNING_SECRET": config.recording_signing_secret,
            "VOICE_OPERATOR_SECRET": config.operator_secret,
            "VENDOR_CONTACT_HASH_SECRET": config.contact_hash_secret,
        }
        weak = [
            name for name, value in secrets.items() if not _secret_is_strong(value)
        ]
        if weak:
            raise ProviderConfigurationError(
                "Real vendor call secrets must be at least "
                f"{MIN_LIVE_SECRET_BYTES} bytes: {', '.join(weak)}"
            )
        assert config.public_api_base_url is not None
        _https_origin("PUBLIC_API_BASE_URL", config.public_api_base_url)
        return config

    def require_openai_config(self) -> OpenAIConfig:
        """Fail closed unless the optional OpenAI boundary is fully enabled."""

        config = self.openai
        if not config.enabled:
            raise ProviderConfigurationError("OpenAI integration requires OPENAI_ENABLED=true")
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
            raise ProviderConfigurationError(f"Missing OpenAI configuration: {', '.join(missing)}")
        return config

    def require_tavily_config(self) -> TavilyConfig:
        """Fail closed unless the optional Tavily boundary is fully enabled."""

        config = self.tavily
        if not config.enabled:
            raise ProviderConfigurationError("Tavily integration requires TAVILY_ENABLED=true")
        if config.api_key is None or not config.api_key.strip():
            raise ProviderConfigurationError("Missing Tavily configuration: TAVILY_API_KEY")
        return config

    def require_supabase_config(self) -> SupabaseConfig:
        """Fail closed unless the persistent repository is fully enabled."""

        config = self.supabase
        if not config.enabled:
            raise ProviderConfigurationError("Supabase integration requires SUPABASE_ENABLED=true")
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
        public_api_base_url = _optional_env("PUBLIC_API_BASE_URL")
        return cls(
            app_mode=app_mode,
            api_host=os.getenv("API_HOST", "127.0.0.1").strip(),
            api_port=int(os.getenv("API_PORT", "8000")),
            cors_allow_origins=_cors_origins_env(),
            live_voice=LiveVoiceConfig(
                api_key=_optional_env("ELEVENLABS_API_KEY"),
                intake_agent_id=_optional_env("ELEVENLABS_INTAKE_AGENT_ID"),
                outbound_agent_id=_outbound_agent_id_env(),
                phone_number_id=_optional_env("ELEVENLABS_PHONE_NUMBER_ID"),
                destination_numbers=_destination_numbers_env(),
                webhook_secret=_optional_env("ELEVENLABS_WEBHOOK_SECRET"),
                precall_secret=_optional_env("ELEVENLABS_PRECALL_SECRET"),
                recording_signing_secret=_optional_env("RECORDING_SIGNING_SECRET"),
                operator_secret=_optional_env("VOICE_OPERATOR_SECRET"),
                public_api_base_url=(
                    _https_origin("PUBLIC_API_BASE_URL", public_api_base_url)
                    if public_api_base_url is not None
                    else None
                ),
                agent_config_version=_optional_env("AGENT_CONFIG_VERSION"),
                live_calls_enabled=_boolean_env("LIVE_CALLS_ENABLED"),
                real_vendor_calls_enabled=_boolean_env(
                    "REAL_VENDOR_CALLS_ENABLED"
                ),
                contact_hash_secret=_optional_env("VENDOR_CONTACT_HASH_SECRET"),
                vendor_consent_max_age_days=_bounded_integer_env(
                    "VENDOR_CONSENT_MAX_AGE_DAYS",
                    default=30,
                    minimum=1,
                    maximum=365,
                ),
                api_base_url=_https_origin(
                    "ELEVENLABS_API_BASE_URL",
                    _optional_env("ELEVENLABS_API_BASE_URL") or "https://api.elevenlabs.io",
                ),
            ),
            openai=OpenAIConfig(
                enabled=_boolean_env("OPENAI_ENABLED"),
                api_key=_optional_env("OPENAI_API_KEY"),
                document_model=(_optional_env("OPENAI_DOCUMENT_MODEL") or "gpt-5.6-luna"),
                recommendation_model=(
                    _optional_env("OPENAI_RECOMMENDATION_MODEL") or "gpt-5.6-terra"
                ),
                api_base_url=_https_origin(
                    "OPENAI_API_BASE_URL",
                    _optional_env("OPENAI_API_BASE_URL") or "https://api.openai.com",
                ),
            ),
            tavily=TavilyConfig(
                enabled=_boolean_env("TAVILY_ENABLED"),
                api_key=_optional_env("TAVILY_API_KEY"),
                api_base_url=_https_origin(
                    "TAVILY_API_BASE_URL",
                    _optional_env("TAVILY_API_BASE_URL") or "https://api.tavily.com",
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
