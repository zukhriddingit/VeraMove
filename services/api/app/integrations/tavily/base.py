"""Protocols for search-backed vendor discovery."""

from typing import Any, Literal, Protocol

from services.api.app.contracts import Vendor, VendorSearchQuery


class VendorDiscoveryGateway(Protocol):
    source: Literal["synthetic_mock", "tavily"]

    def discover(self, origin: str | None, destination: str | None) -> list[Vendor]: ...

    def source_call_list(self, query: VendorSearchQuery) -> list[Vendor]: ...


class TavilySearchClient(Protocol):
    def search(self, *, query: str, max_results: int) -> list[dict[str, Any]]: ...


class TavilyJsonTransport(Protocol):
    """Minimal injected JSON transport used by the live search client."""

    def post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> Any: ...
