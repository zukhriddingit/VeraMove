"""Shared fixtures for the mock API test suite."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from services.api.app.api.dependencies import get_repository
from services.api.app.integrations.elevenlabs.mock import MockVoiceProvider
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.main import app
from services.api.app.orchestration.fixtures import DemoFixtures
from services.api.app.orchestration.mock_intelligence import MockIntelligenceProvider
from services.api.app.orchestration.service import VeraMoveService
from services.api.app.repositories.memory import InMemoryRepository

FIXED_NOW = datetime(2026, 7, 18, 16, 0, tzinfo=UTC)


@pytest.fixture
def fixtures() -> DemoFixtures:
    return DemoFixtures()


@pytest.fixture
def job_spec(fixtures: DemoFixtures):
    return fixtures.load_job()


@pytest.fixture
def job_spec_payload(job_spec):
    return job_spec.model_dump(mode="json")


@pytest.fixture
def service(fixtures: DemoFixtures) -> VeraMoveService:
    repository = InMemoryRepository()
    return VeraMoveService(
        jobs=repository,
        calls=repository,
        quotes=repository,
        voice=MockVoiceProvider(fixtures),
        intelligence=MockIntelligenceProvider(
            fixtures,
            MockNegotiationGateway(fixtures),
        ),
        discovery=MockVendorDiscoveryGateway(fixtures),
        fixtures=fixtures,
        clock=lambda: FIXED_NOW,
    )


@pytest.fixture(autouse=True)
def reset_api_repository() -> Iterator[None]:
    get_repository().reset()
    yield
    get_repository().reset()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
