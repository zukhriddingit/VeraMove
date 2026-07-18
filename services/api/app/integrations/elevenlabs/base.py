"""Shared transport boundaries for ElevenLabs adapters."""

from typing import Any, Protocol


class JsonHttpTransport(Protocol):
    """Small injectable JSON boundary that keeps orchestration network-free."""

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...
