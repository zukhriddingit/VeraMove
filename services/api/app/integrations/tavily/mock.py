"""Synthetic cached Tavily boundaries with no network requests."""

from pydantic import HttpUrl

from services.api.app.contracts import Vendor, VendorSearchQuery
from services.api.app.integrations.tavily.base import ExtractedWebPage
from services.api.app.orchestration.fixtures import DemoFixtures


class MockVendorDiscoveryGateway:
    source = "synthetic_mock"

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


class MockTavilyExtractClient:
    """Return bounded synthetic webpage text for one to three trusted URLs."""

    def extract(
        self,
        urls: tuple[HttpUrl, ...],
    ) -> dict[str, ExtractedWebPage | None]:
        return {
            str(url): ExtractedWebPage(
                url=url,
                content=(
                    "Synthetic mover website advertises local moving services. "
                    "All prices and terms must be confirmed during the role-play call."
                ),
                truncated=False,
            )
            for url in urls
        }


__all__ = ["MockTavilyExtractClient", "MockVendorDiscoveryGateway"]
