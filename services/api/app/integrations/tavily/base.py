"""Protocols and bounded values for search-backed vendor research."""

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import HttpUrl

from services.api.app.contracts import Vendor, VendorSearchQuery


class VendorDiscoveryGateway(Protocol):
    source: Literal["synthetic_mock", "tavily"]

    def discover(self, origin: str | None, destination: str | None) -> list[Vendor]: ...

    def source_call_list(self, query: VendorSearchQuery) -> list[Vendor]: ...


class TavilySearchClient(Protocol):
    def search(self, *, query: str, max_results: int) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class ExtractedWebPage:
    """One already-bounded webpage returned by the provider boundary."""

    url: HttpUrl
    content: str
    truncated: bool


class TavilyExtractClient(Protocol):
    def extract(
        self,
        urls: tuple[HttpUrl, HttpUrl, HttpUrl],
    ) -> dict[str, ExtractedWebPage | None]: ...


class TavilyJsonTransport(Protocol):
    """Minimal injected JSON transport used by the live search client."""

    def post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> Any: ...
