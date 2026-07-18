"""Synthetic vendor discovery with no search requests."""

from services.api.app.contracts import Vendor
from services.api.app.orchestration.fixtures import DemoFixtures


class MockVendorDiscoveryGateway:
    def __init__(self, fixtures: DemoFixtures) -> None:
        self._fixtures = fixtures

    def discover(self, origin: str | None, destination: str | None) -> list[Vendor]:
        del origin, destination
        return self._fixtures.load_vendors()
