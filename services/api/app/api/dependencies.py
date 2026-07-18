"""Application wiring for the credential-free mock lifecycle."""

from datetime import UTC, datetime
from functools import lru_cache

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
    fixtures = DemoFixtures()
    return VeraMoveService(
        jobs=_repository,
        calls=_repository,
        quotes=_repository,
        voice=MockVoiceProvider(fixtures),
        intelligence=MockIntelligenceProvider(
            fixtures,
            MockNegotiationGateway(fixtures),
        ),
        discovery=MockVendorDiscoveryGateway(fixtures),
        fixtures=fixtures,
        clock=mock_now,
    )
