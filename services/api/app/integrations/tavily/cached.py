"""Cached Tavily normalization without storing unnecessary contact information."""

from __future__ import annotations

from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

from services.api.app.contracts import (
    DataClassification,
    ProvenanceReference,
    ProvenanceType,
    Vendor,
    VendorSearchQuery,
)
from services.api.app.integrations.tavily.base import TavilySearchClient


class CachedTavilyVendorDiscovery:
    def __init__(
        self,
        client: TavilySearchClient,
        max_results: int = 10,
        role_play: bool = True,
    ) -> None:
        self._client = client
        self._max_results = max_results
        self._role_play = role_play
        self._cache: dict[tuple[str, str, str, int], list[Vendor]] = {}

    def source_call_list(self, query: VendorSearchQuery) -> list[Vendor]:
        key = (
            query.city.casefold(),
            query.state.casefold(),
            query.service_type.casefold(),
            query.radius_miles,
        )
        if key not in self._cache:
            phrase = (
                f"{query.service_type} companies in {query.city}, {query.state} "
                f"within {query.radius_miles} miles"
            )
            results = self._client.search(query=phrase, max_results=self._max_results)
            self._cache[key] = [
                self._normalize(item, query)
                for item in results
                if item.get("title") and item.get("url")
            ]
        return [vendor.model_copy(deep=True) for vendor in self._cache[key]]

    def discover(self, origin: str | None, destination: str | None) -> list[Vendor]:
        city = origin or destination
        if city is None:
            raise ValueError("origin or destination is required")
        return self.source_call_list(VendorSearchQuery(city=city, state="Unknown"))

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def _normalize(self, result: dict, query: VendorSearchQuery) -> Vendor:
        url = str(result["url"])
        name = str(result["title"]).strip()
        host = urlparse(url).netloc.casefold().removeprefix("www.")
        slug_seed = "".join(character if character.isalnum() else "-" for character in name.lower())
        slug = "-".join(part for part in slug_seed.split("-") if part)[:80]
        classification = (
            DataClassification.ROLE_PLAY if self._role_play else DataClassification.REAL_REDACTED
        )
        production_contact_label = (
            "Production call-list example; direct contact details intentionally not stored."
        )
        return Vendor(
            vendor_id=uuid5(NAMESPACE_URL, url),
            name=name,
            slug=slug or uuid5(NAMESPACE_URL, url).hex,
            behavior_summary=(
                "Production call-list example sourced from Tavily; no behavior is inferred."
            ),
            contact_label=(
                "Role-play call-list example; direct contact details intentionally not stored."
                if self._role_play
                else production_contact_label
            ),
            service_areas=[f"{query.city}, {query.state} ({query.radius_miles}-mile query)"],
            data_classification=classification,
            provenance=[
                ProvenanceReference(
                    source_type=ProvenanceType.TAVILY,
                    source_id=host or url,
                    location=url,
                )
            ],
        )
