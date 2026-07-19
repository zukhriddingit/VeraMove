"""Request-shape and failure tests for the live Tavily search client."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.tavily.cached import CachedTavilyVendorDiscovery
from services.api.app.integrations.tavily.live import (
    HttpxTavilyTransport,
    TavilyHttpClient,
)


class RecordingTransport:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[
            tuple[str, dict[str, str], dict[str, object]]
        ] = []

    def post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> Any:
        self.requests.append((url, headers, payload))
        if self.error is not None:
            raise self.error
        return self.response


class FakeHttpxResponse:
    def __init__(self, status_code: int = 200, json_body: Any = None) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.request = httpx.Request("POST", "https://api.tavily.example/search")
        self.response = httpx.Response(status_code, request=self.request)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "provider-body=synthetic-tavily-key",
                request=self.request,
                response=self.response,
            )

    def json(self) -> Any:
        if isinstance(self._json_body, Exception):
            raise self._json_body
        return self._json_body


def test_tavily_http_client_uses_private_bounded_search_options():
    transport = RecordingTransport(
        {
            "results": [
                {
                    "title": "Synthetic Movers",
                    "url": "https://vendor.example",
                    "content": "This search snippet must not leave the client.",
                    "raw_content": "This raw page must not leave the client.",
                }
            ],
            "answer": "This generated answer must not leave the client.",
            "usage": {"credits": 1},
        }
    )
    client = TavilyHttpClient(
        api_key="synthetic-tavily-key",
        api_base_url="https://api.tavily.example",
        transport=transport,
    )

    results = client.search(
        query="moving companies in Example City",
        max_results=10,
    )

    assert results == [
        {"title": "Synthetic Movers", "url": "https://vendor.example"}
    ]
    url, headers, payload = transport.requests[0]
    assert url == "https://api.tavily.example/search"
    assert headers["Authorization"] == "Bearer synthetic-tavily-key"
    assert payload == {
        "query": "moving companies in Example City",
        "search_depth": "basic",
        "topic": "general",
        "max_results": 10,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    }


def test_live_gateway_reports_tavily_and_preserves_only_source_provenance():
    transport = RecordingTransport(
        {
            "results": [
                {
                    "title": f"Synthetic Vendor {index}",
                    "url": f"https://vendor-{index}.example/moving",
                    "content": "Unpersisted search content",
                }
                for index in range(3)
            ]
        }
    )
    gateway = CachedTavilyVendorDiscovery(
        TavilyHttpClient(
            api_key="synthetic-tavily-key",
            api_base_url="https://api.tavily.example",
            transport=transport,
        )
    )

    vendors = gateway.discover("Example City", None)

    assert gateway.source == "tavily"
    assert len(vendors) == 3
    assert all(vendor.provenance[0].source_type.value == "tavily" for vendor in vendors)
    assert all(vendor.provenance[0].excerpt is None for vendor in vendors)


@pytest.mark.parametrize(
    ("title", "expected_slug"),
    [
        ("Möving & Storage – Boston", "moving-storage-boston"),
        ("A" * 79 + " Moving Company", "a" * 79),
        ("東京引越センター", "vendor-62e9c2cdec9e5a0ca67b92e18f69d79e"),
    ],
)
def test_live_gateway_normalizes_provider_titles_to_contract_safe_slugs(
    title,
    expected_slug,
):
    transport = RecordingTransport(
        {
            "results": [
                {
                    "title": title,
                    "url": "https://unicode-vendor.example/moving",
                }
            ]
        }
    )
    gateway = CachedTavilyVendorDiscovery(
        TavilyHttpClient(
            api_key="synthetic-tavily-key",
            api_base_url="https://api.tavily.example",
            transport=transport,
        )
    )

    vendor = gateway.discover("Example City", None)[0]

    assert vendor.slug == expected_slug
    assert len(vendor.slug) <= 80


@pytest.mark.parametrize("status_code", [401, 429, 503])
def test_httpx_transport_maps_http_errors_to_exact_safe_message(
    monkeypatch,
    status_code,
):
    monkeypatch.setattr(
        "services.api.app.integrations.tavily.live.httpx.post",
        lambda *args, **kwargs: FakeHttpxResponse(status_code),
    )

    with pytest.raises(ProviderRequestError) as raised:
        HttpxTavilyTransport().post(
            "https://api.tavily.example/search",
            {"Authorization": "Bearer synthetic-tavily-key"},
            {"query": "moving companies in Example City"},
        )

    assert str(raised.value) == "Tavily search failed"
    assert "synthetic-tavily-key" not in str(raised.value)


def test_httpx_transport_maps_invalid_json_to_exact_safe_message(monkeypatch):
    monkeypatch.setattr(
        "services.api.app.integrations.tavily.live.httpx.post",
        lambda *args, **kwargs: FakeHttpxResponse(
            json_body=ValueError("provider-body=synthetic-tavily-key")
        ),
    )

    with pytest.raises(ProviderRequestError) as raised:
        HttpxTavilyTransport().post(
            "https://api.tavily.example/search",
            {"Authorization": "Bearer synthetic-tavily-key"},
            {"query": "moving companies in Example City"},
        )

    assert str(raised.value) == "Tavily search failed"
    assert "synthetic-tavily-key" not in str(raised.value)


def test_httpx_transport_maps_timeout_to_exact_safe_message(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("provider-body=synthetic-tavily-key")

    monkeypatch.setattr(
        "services.api.app.integrations.tavily.live.httpx.post",
        raise_timeout,
    )

    with pytest.raises(ProviderRequestError) as raised:
        HttpxTavilyTransport().post(
            "https://api.tavily.example/search",
            {"Authorization": "Bearer synthetic-tavily-key"},
            {"query": "moving companies in Example City"},
        )

    assert str(raised.value) == "Tavily search failed"
    assert "synthetic-tavily-key" not in str(raised.value)


def test_tavily_client_defaults_to_httpx_transport(monkeypatch):
    requests = []

    def fake_post(self, url, headers, payload):
        del self
        requests.append((url, headers, payload))
        return {"results": []}

    monkeypatch.setattr(HttpxTavilyTransport, "post", fake_post)
    client = TavilyHttpClient(
        api_key="synthetic-tavily-key",
        api_base_url="https://api.tavily.example",
    )

    assert client.search(query="moving companies in Example City", max_results=3) == []
    assert len(requests) == 1


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        {},
        {"results": None},
        {"results": {}},
        {"results": ["not-an-object"]},
    ],
)
def test_tavily_http_client_rejects_malformed_envelopes(response):
    client = TavilyHttpClient(
        api_key="synthetic-tavily-key",
        api_base_url="https://api.tavily.example",
        transport=RecordingTransport(response),
    )

    with pytest.raises(ProviderRequestError, match="malformed response"):
        client.search(query="moving companies in Example City", max_results=3)


def test_tavily_http_client_maps_transport_failures_without_exposing_key():
    client = TavilyHttpClient(
        api_key="synthetic-tavily-key",
        api_base_url="https://api.tavily.example",
        transport=RecordingTransport(error=TimeoutError("synthetic-tavily-key")),
    )

    with pytest.raises(ProviderRequestError, match="Tavily search failed") as raised:
        client.search(query="moving companies in Example City", max_results=3)

    assert "synthetic-tavily-key" not in str(raised.value)


@pytest.mark.parametrize("max_results", [0, 21])
def test_tavily_http_client_rejects_unbounded_result_counts(max_results):
    client = TavilyHttpClient(
        api_key="synthetic-tavily-key",
        api_base_url="https://api.tavily.example",
        transport=RecordingTransport({"results": []}),
    )

    with pytest.raises(ProviderRequestError, match="between 1 and 20"):
        client.search(query="moving companies in Example City", max_results=max_results)
