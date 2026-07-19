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


class ConversationHttpTransport(Protocol):
    """Injectable read boundary for conversation details and audio."""

    def get_json(
        self,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...

    def get_bytes(
        self,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> tuple[bytes, str]: ...
