"""Cached Tavily normalization without storing unnecessary contact information."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

from services.api.app.contracts import (
    DataClassification,
    ProvenanceReference,
    ProvenanceType,
    Vendor,
    VendorSearchQuery,
)
from services.api.app.integrations.tavily.base import TavilySearchClient


def _contract_safe_slug(name: str, url: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")[:80].rstrip("-")
    return slug or f"vendor-{uuid5(NAMESPACE_URL, url).hex}"


class CachedTavilyVendorDiscovery:
    source = "tavily"

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
            normalized: list[Vendor] = []
            seen_hosts: set[str] = set()
            for item in results:
                title = item.get("title")
                raw_url = item.get("url")
                if not title or not raw_url:
                    continue
                url = self._safe_https_url(str(raw_url))
                if url is None:
                    continue
                host = urlparse(url).netloc.casefold().removeprefix("www.")
                if host in seen_hosts:
                    continue
                seen_hosts.add(host)
                normalized.append(self._normalize(str(title), url, query))
            self._cache[key] = normalized
        return [vendor.model_copy(deep=True) for vendor in self._cache[key]]

    def discover(self, origin: str | None, destination: str | None) -> list[Vendor]:
        city = origin or destination
        if city is None:
            raise ValueError("origin or destination is required")
        return self.source_call_list(VendorSearchQuery(city=city, state="Unknown"))

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    @staticmethod
    def _safe_https_url(raw_url: str) -> str | None:
        parsed = urlsplit(raw_url.strip())
        if parsed.scheme.casefold() != "https" or not parsed.netloc:
            return None
        return urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, ""))

    def _normalize(self, name: str, url: str, query: VendorSearchQuery) -> Vendor:
        name = name.strip()
        host = urlparse(url).netloc.casefold().removeprefix("www.")
        slug = _contract_safe_slug(name, url)
        classification = (
            DataClassification.ROLE_PLAY if self._role_play else DataClassification.REAL_REDACTED
        )
        production_contact_label = (
            "Production call-list example; direct contact details intentionally not stored."
        )
        return Vendor(
            vendor_id=uuid5(NAMESPACE_URL, url),
            name=name,
            slug=slug,
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
