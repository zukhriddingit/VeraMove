"""Application wiring for the credential-free mock lifecycle."""

from datetime import UTC, datetime
from functools import lru_cache

from services.api.app.core.config import Settings
from services.api.app.core.errors import ProviderConfigurationError
from services.api.app.integrations.elevenlabs.base import JsonHttpTransport
from services.api.app.integrations.elevenlabs.live import (
    ElevenLabsVoiceProvider,
    HttpxJsonTransport,
)
from services.api.app.integrations.elevenlabs.mock import MockVoiceProvider
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.orchestration.fixtures import DemoFixtures
from services.api.app.orchestration.mock_intelligence import MockIntelligenceProvider
from services.api.app.orchestration.service import VeraMoveService
from services.api.app.repositories.memory import InMemoryRepository

_repository = InMemoryRepository()


def get_repository() -> InMemoryRepository:
    return _repository


def mock_now() -> datetime:
    """Keep synthetic provider timestamps ordered and demo responses deterministic."""

    return datetime(2026, 7, 18, 16, 0, tzinfo=UTC)


@lru_cache
def get_service() -> VeraMoveService:
    return build_service(Settings.from_env(), _repository)


def build_service(
    settings: Settings,
    repository: InMemoryRepository,
    voice_transport: JsonHttpTransport | None = None,
) -> VeraMoveService:
    """Compose mock or live boundaries without initiating provider activity."""

    fixtures = DemoFixtures()
    if settings.app_mode == "mock":
        voice = MockVoiceProvider(fixtures)
    elif settings.app_mode == "live":
        voice = ElevenLabsVoiceProvider(
            settings,
            (
                voice_transport
                if voice_transport is not None
                else HttpxJsonTransport()
            ),
        )
    else:
        raise ProviderConfigurationError("APP_MODE must be either mock or live")
    return VeraMoveService(
        jobs=repository,
        calls=repository,
        quotes=repository,
        voice=voice,
        intelligence=MockIntelligenceProvider(
            fixtures,
            MockNegotiationGateway(fixtures),
        ),
        discovery=MockVendorDiscoveryGateway(fixtures),
        fixtures=fixtures,
        clock=mock_now,
    )
