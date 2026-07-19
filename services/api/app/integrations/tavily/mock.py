"""Synthetic cached vendor discovery with no search requests."""

from services.api.app.contracts import Vendor, VendorSearchQuery
from services.api.app.orchestration.fixtures import DemoFixtures


class MockVendorDiscoveryGateway:
    def __init__(self, fixtures: DemoFixtures) -> None:
        self._fixtures = fixtures
        self._cache: dict[tuple[str, str, str, int], list[Vendor]] = {}

    def discover(self, origin: str | None, destination: str | None) -> list[Vendor]:
        del origin, destination
        return self._fixtures.load_vendors()

    def source_call_list(self, query: VendorSearchQuery) -> list[Vendor]:
        key = (
            query.city.casefold(),
            query.state.casefold(),
            query.service_type.casefold(),
            query.radius_miles,
        )
        if key not in self._cache:
            self._cache[key] = self._fixtures.load_vendors()
        return [vendor.model_copy(deep=True) for vendor in self._cache[key]]

    @property
    def cache_size(self) -> int:
        return len(self._cache)
