"""Fail-closed Tavily Search API client with privacy-preserving options."""

from __future__ import annotations

from typing import Any

import httpx

from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.tavily.base import TavilyJsonTransport


class HttpxTavilyTransport:
    """Production JSON transport with a bounded timeout and safe errors."""

    def post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> Any:
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError("Tavily search failed") from exc


class TavilyHttpClient:
    """Return only title and URL from one bounded Tavily search request."""

    def __init__(
        self,
        api_key: str,
        api_base_url: str,
        transport: TavilyJsonTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_base_url = api_base_url.rstrip("/")
        self._transport = (
            transport if transport is not None else HttpxTavilyTransport()
        )

    def search(self, *, query: str, max_results: int) -> list[dict[str, Any]]:
        if not 1 <= max_results <= 20:
            raise ProviderRequestError("Tavily max_results must be between 1 and 20")
        if not query.strip():
            raise ProviderRequestError("Tavily search query is required")

        try:
            response = self._transport.post(
                f"{self._api_base_url}/search",
                {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                {
                    "query": query,
                    "search_depth": "basic",
                    "topic": "general",
                    "max_results": max_results,
                    "include_answer": False,
                    "include_raw_content": False,
                    "include_images": False,
                },
            )
        except ProviderRequestError:
            raise
        except Exception as exc:
            raise ProviderRequestError("Tavily search failed") from exc

        if not isinstance(response, dict):
            raise ProviderRequestError("Tavily returned a malformed response")
        results = response.get("results")
        if not isinstance(results, list) or not all(
            isinstance(result, dict) for result in results
        ):
            raise ProviderRequestError("Tavily returned a malformed response")
        return [
            {"title": result.get("title"), "url": result.get("url")}
            for result in results
        ]
