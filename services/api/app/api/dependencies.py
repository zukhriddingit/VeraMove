"""Application wiring for the mock-only starter."""

from functools import lru_cache

from services.api.app.integrations.elevenlabs.mock import MockVoiceVendorGateway
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.orchestration.fixtures import DemoFixtures
from services.api.app.orchestration.service import VeraMoveService
from services.api.app.repositories.memory import InMemoryJobRepository

_repository = InMemoryJobRepository()


def get_repository() -> InMemoryJobRepository:
    return _repository


@lru_cache
def get_service() -> VeraMoveService:
    fixtures = DemoFixtures()
    return VeraMoveService(
        repository=_repository,
        voice_gateway=MockVoiceVendorGateway(fixtures),
        negotiation_gateway=MockNegotiationGateway(fixtures),
        discovery_gateway=MockVendorDiscoveryGateway(fixtures),
        fixtures=fixtures,
    )
