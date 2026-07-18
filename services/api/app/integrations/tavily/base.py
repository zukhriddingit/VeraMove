"""Protocols for search-backed vendor discovery."""

from typing import Any, Protocol

from services.api.app.contracts import Vendor, VendorSearchQuery


class VendorDiscoveryGateway(Protocol):
    def discover(self, origin: str | None, destination: str | None) -> list[Vendor]: ...

    def source_call_list(self, query: VendorSearchQuery) -> list[Vendor]: ...


class TavilySearchClient(Protocol):
    def search(self, *, query: str, max_results: int) -> list[dict[str, Any]]: ...
