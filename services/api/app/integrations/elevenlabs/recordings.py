"""Server-side ElevenLabs recording retrieval with strict audio validation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from services.api.app.core.errors import ProviderRequestError, ResourceNotFound
from services.api.app.integrations.elevenlabs.base import ConversationHttpTransport
from services.api.app.integrations.elevenlabs.conversations import (
    HttpxConversationTransport,
    _conversation_id,
)

ALLOWED_AUDIO_TYPES = frozenset(
    {"audio/mpeg", "audio/mp3", "audio/mp4", "audio/wav", "audio/x-wav"}
)
MAX_RECORDING_BYTES = 25_000_000


class RecordingAudio(BaseModel):
    """Transient validated bytes returned directly to a streaming response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: bytes = Field(min_length=1, max_length=MAX_RECORDING_BYTES)
    media_type: str


class ElevenLabsRecordingClient:
    def __init__(
        self,
        api_key: str,
        api_base_url: str = "https://api.elevenlabs.io",
        transport: ConversationHttpTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_base_url = api_base_url.rstrip("/")
        self._transport = transport or HttpxConversationTransport()

    def fetch_audio(
        self,
        conversation_id: str,
        *,
        has_audio: bool,
    ) -> RecordingAudio:
        if not has_audio:
            raise ResourceNotFound("ElevenLabs conversation has no saved recording")
        safe_id = _conversation_id(conversation_id)
        content, raw_media_type = self._transport.get_bytes(
            f"{self._api_base_url}/v1/convai/conversations/{safe_id}/audio",
            {"xi-api-key": self._api_key},
            30.0,
        )
        media_type = raw_media_type.split(";", 1)[0].strip().lower()
        if media_type not in ALLOWED_AUDIO_TYPES:
            raise ProviderRequestError("ElevenLabs returned an unsupported recording type")
        if not content:
            raise ResourceNotFound("ElevenLabs recording was empty")
        if len(content) > MAX_RECORDING_BYTES:
            raise ProviderRequestError("ElevenLabs recording exceeded the size limit")
        return RecordingAudio(content=content, media_type=media_type)
