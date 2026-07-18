"""Shared fixtures for the mock API test suite."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from services.api.app.api.dependencies import get_repository
from services.api.app.integrations.elevenlabs.mock import MockVoiceVendorGateway
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.main import app
from services.api.app.orchestration.fixtures import DemoFixtures
from services.api.app.orchestration.service import VeraMoveService
from services.api.app.repositories.memory import InMemoryJobRepository


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
    repository = InMemoryJobRepository()
    return VeraMoveService(
        repository=repository,
        voice_gateway=MockVoiceVendorGateway(fixtures),
        negotiation_gateway=MockNegotiationGateway(fixtures),
        discovery_gateway=MockVendorDiscoveryGateway(fixtures),
        fixtures=fixtures,
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
