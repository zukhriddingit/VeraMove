"""Fail-closed Tavily Extract client for three server-selected HTTPS pages."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import HttpUrl

from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.tavily.base import (
    ExtractedWebPage,
    TavilyJsonTransport,
)

MAX_EXTRACTED_CHARACTERS = 40_000


class HttpxTavilyExtractTransport:
    """Production transport with a client timeout longer than Tavily's request timeout."""

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
                timeout=25.0,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError("Tavily extraction failed") from exc


class TavilyHttpExtractClient:
    """Extract exactly three trusted pages and return only capped text."""

    def __init__(
        self,
        api_key: str,
        api_base_url: str,
        transport: TavilyJsonTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_base_url = api_base_url.rstrip("/")
        self._transport = transport or HttpxTavilyExtractTransport()

    def extract(
        self,
        urls: tuple[HttpUrl, HttpUrl, HttpUrl],
    ) -> dict[str, ExtractedWebPage | None]:
        normalized = [str(url) for url in urls]
        if len(normalized) != 3 or len(set(normalized)) != 3:
            raise ProviderRequestError(
                "Tavily extraction requires exactly three distinct URLs"
            )
        if any(url.scheme != "https" for url in urls):
            raise ProviderRequestError("Tavily extraction requires HTTPS URLs")

        try:
            response = self._transport.post(
                f"{self._api_base_url}/extract",
                {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                {
                    "urls": normalized,
                    "extract_depth": "basic",
                    "include_images": False,
                    "format": "markdown",
                    "timeout": 20.0,
                },
            )
        except ProviderRequestError:
            raise
        except Exception as exc:
            raise ProviderRequestError("Tavily extraction failed") from exc

        return self._parse(response, urls)

    @staticmethod
    def _parse(
        response: Any,
        urls: tuple[HttpUrl, HttpUrl, HttpUrl],
    ) -> dict[str, ExtractedWebPage | None]:
        if not isinstance(response, dict):
            raise ProviderRequestError("Tavily returned a malformed extract response")
        results = response.get("results")
        failed_results = response.get("failed_results", [])
        if not isinstance(results, list) or not isinstance(failed_results, list):
            raise ProviderRequestError("Tavily returned a malformed extract response")
        if not all(isinstance(item, dict) for item in [*results, *failed_results]):
            raise ProviderRequestError("Tavily returned a malformed extract response")

        requested = {str(url): url for url in urls}
        parsed: dict[str, ExtractedWebPage | None] = {
            key: None for key in requested
        }
        seen: set[str] = set()
        for item in results:
            result_url = item.get("url")
            content = item.get("raw_content")
            if (
                not isinstance(result_url, str)
                or result_url not in requested
                or result_url in seen
                or not isinstance(content, str)
            ):
                raise ProviderRequestError(
                    "Tavily returned a malformed extract response"
                )
            seen.add(result_url)
            if not content.strip():
                continue
            truncated = len(content) > MAX_EXTRACTED_CHARACTERS
            parsed[result_url] = ExtractedWebPage(
                url=requested[result_url],
                content=content[:MAX_EXTRACTED_CHARACTERS],
                truncated=truncated,
            )

        for item in failed_results:
            failed_url = item.get("url")
            if (
                not isinstance(failed_url, str)
                or failed_url not in requested
                or failed_url in seen
            ):
                raise ProviderRequestError(
                    "Tavily returned a malformed extract response"
                )
            seen.add(failed_url)

        return parsed


__all__ = ["HttpxTavilyExtractTransport", "TavilyHttpExtractClient"]
