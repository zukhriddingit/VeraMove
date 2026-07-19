"""Issue short-lived ElevenLabs WebRTC tokens without exposing credentials."""

from __future__ import annotations

from typing import Protocol
from urllib.parse import urlencode

from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.elevenlabs.base import ConversationHttpTransport
from services.api.app.integrations.elevenlabs.conversations import (
    HttpxConversationTransport,
)


class BrowserVoiceTokenIssuer(Protocol):
    """Narrow dependency boundary used by the FastAPI intake route."""

    def issue_token(self) -> str: ...


class ElevenLabsBrowserVoiceTokenClient:
    """Request one authenticated WebRTC token for the configured Intake Agent."""

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        api_base_url: str = "https://api.elevenlabs.io",
        transport: ConversationHttpTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._agent_id = agent_id
        self._api_base_url = api_base_url.rstrip("/")
        self._transport = transport or HttpxConversationTransport()

    def issue_token(self) -> str:
        query = urlencode({"agent_id": self._agent_id})
        payload = self._transport.get_json(
            f"{self._api_base_url}/v1/convai/conversation/token?{query}",
            {"xi-api-key": self._api_key},
            10.0,
        )
        token = payload.get("token")
        if not isinstance(token, str) or not token.strip() or len(token) > 8_192:
            raise ProviderRequestError(
                "ElevenLabs returned an invalid browser voice token"
            )
        return token.strip()
