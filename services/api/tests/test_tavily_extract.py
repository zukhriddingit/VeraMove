"""Bounded Tavily Extract requests without external network calls."""

from typing import Any

import pytest
from pydantic import HttpUrl

from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.tavily.extract import TavilyHttpExtractClient


class RecordingTransport:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.requests: list[tuple[str, dict[str, str], dict[str, object]]] = []

    def post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> Any:
        self.requests.append((url, headers, payload))
        return self.response


def _urls() -> tuple[HttpUrl, HttpUrl, HttpUrl]:
    return (
        HttpUrl("https://a.example"),
        HttpUrl("https://b.example"),
        HttpUrl("https://c.example"),
    )


def _client(transport: RecordingTransport) -> TavilyHttpExtractClient:
    return TavilyHttpExtractClient(
        api_key="synthetic-key",
        api_base_url="https://api.tavily.example",
        transport=transport,
    )


def test_extract_posts_exactly_three_https_urls_with_bounded_options():
    transport = RecordingTransport(
        {
            "results": [
                {"url": str(url), "raw_content": f"Content for {url.host}"}
                for url in _urls()
            ],
            "failed_results": [],
        }
    )

    pages = _client(transport).extract(_urls())

    url, headers, payload = transport.requests[0]
    assert url == "https://api.tavily.example/extract"
    assert headers["Authorization"] == "Bearer synthetic-key"
    assert payload == {
        "urls": [str(url) for url in _urls()],
        "extract_depth": "basic",
        "include_images": False,
        "format": "markdown",
        "timeout": 20.0,
    }
    assert set(pages) == {str(url) for url in _urls()}
    assert all(page is not None for page in pages.values())


def test_extract_preserves_success_when_one_url_fails():
    urls = _urls()
    transport = RecordingTransport(
        {
            "results": [
                {"url": str(urls[0]), "raw_content": "Rate $149"},
                {"url": str(urls[2]), "raw_content": "Packing is available"},
            ],
            "failed_results": [
                {"url": str(urls[1]), "error": "provider detail must not escape"}
            ],
        }
    )

    pages = _client(transport).extract(urls)

    assert pages[str(urls[0])] is not None
    assert pages[str(urls[1])] is None
    assert pages[str(urls[2])] is not None


def test_extract_truncates_content_before_returning_it():
    urls = _urls()
    transport = RecordingTransport(
        {
            "results": [
                {"url": str(url), "raw_content": "x" * 40_001}
                for url in urls
            ],
            "failed_results": [],
        }
    )

    pages = _client(transport).extract(urls)

    assert all(page is not None and len(page.content) == 40_000 for page in pages.values())
    assert all(page is not None and page.truncated for page in pages.values())


@pytest.mark.parametrize(
    "urls",
    [
        (),
        (
            HttpUrl("https://a.example"),
            HttpUrl("https://a.example"),
            HttpUrl("https://c.example"),
        ),
        (
            HttpUrl("https://a.example"),
            HttpUrl("https://b.example"),
            HttpUrl("https://c.example"),
            HttpUrl("https://d.example"),
        ),
        (
            HttpUrl("http://a.example"),
            HttpUrl("https://b.example"),
            HttpUrl("https://c.example"),
        ),
    ],
)
def test_extract_rejects_unsafe_or_out_of_bounds_url_input(urls):
    with pytest.raises(ProviderRequestError):
        _client(RecordingTransport({})).extract(urls)  # type: ignore[arg-type]


def test_extract_allows_a_scoped_single_url_retry():
    url = HttpUrl("https://a.example")
    transport = RecordingTransport(
        {
            "results": [{"url": str(url), "raw_content": "Rate $149"}],
            "failed_results": [],
        }
    )

    pages = _client(transport).extract((url,))

    assert pages[str(url)] is not None


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {"results": "not-a-list"},
        {"results": [{"url": "https://unknown.example", "raw_content": "x"}]},
        {"results": [{"url": "https://a.example/", "raw_content": 7}]},
    ],
)
def test_extract_rejects_malformed_provider_envelopes(response):
    with pytest.raises(ProviderRequestError, match="malformed"):
        _client(RecordingTransport(response)).extract(_urls())


def test_extract_translates_unexpected_transport_failure():
    class FailingTransport:
        def post(self, url, headers, payload):
            raise RuntimeError("secret provider detail")

    with pytest.raises(ProviderRequestError, match="Tavily extraction failed") as raised:
        TavilyHttpExtractClient(
            api_key="synthetic",
            api_base_url="https://api.tavily.example",
            transport=FailingTransport(),
        ).extract(_urls())
    assert "secret provider detail" not in str(raised.value)
