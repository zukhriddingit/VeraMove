"""Safe ElevenLabs conversation-detail retrieval for explicit repair operations."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from services.api.app.core.errors import ProviderRequestError, ResourceNotFound
from services.api.app.integrations.elevenlabs.analysis import (
    parse_post_call_transcription,
)
from services.api.app.integrations.elevenlabs.base import ConversationHttpTransport
from services.api.app.integrations.elevenlabs.models import VerifiedPostCallTranscription

CONVERSATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,200}$")


def utc_now() -> datetime:
    return datetime.now(UTC)


class ConversationRepairSnapshot(BaseModel):
    """Allowlisted details suitable for routing through canonical materialization."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=200)
    status: Literal["initiated", "in-progress", "processing", "done", "failed"]
    has_audio: bool = False
    completed_event: VerifiedPostCallTranscription | None = None


class HttpxConversationTransport:
    """Read provider resources while translating every failure to safe domain errors."""

    def get_json(
        self,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, object]:
        try:
            response = httpx.get(url, headers=headers, timeout=timeout_seconds)
            if response.status_code == 404:
                raise ResourceNotFound("ElevenLabs conversation was not found")
            response.raise_for_status()
            payload = response.json()
        except ResourceNotFound:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError("ElevenLabs conversation request failed") from exc
        if not isinstance(payload, dict):
            raise ProviderRequestError("ElevenLabs returned invalid conversation details")
        return payload

    def get_bytes(
        self,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> tuple[bytes, str]:
        try:
            response = httpx.get(url, headers=headers, timeout=timeout_seconds)
            if response.status_code == 404:
                raise ResourceNotFound("ElevenLabs recording was not found")
            response.raise_for_status()
        except ResourceNotFound:
            raise
        except httpx.HTTPError as exc:
            raise ProviderRequestError("ElevenLabs recording request failed") from exc
        return response.content, response.headers.get("content-type", "")


class ElevenLabsConversationClient:
    """Fetch one conversation without retaining provider metadata or phone fields."""

    def __init__(
        self,
        api_key: str,
        api_base_url: str = "https://api.elevenlabs.io",
        transport: ConversationHttpTransport | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._api_key = api_key
        self._api_base_url = api_base_url.rstrip("/")
        self._transport = transport or HttpxConversationTransport()
        self._clock = clock

    def fetch_for_repair(self, conversation_id: str) -> ConversationRepairSnapshot:
        safe_id = _conversation_id(conversation_id)
        payload = self._transport.get_json(
            f"{self._api_base_url}/v1/convai/conversations/{safe_id}",
            {"xi-api-key": self._api_key},
            15.0,
        )
        if not isinstance(payload, dict):
            raise ProviderRequestError("ElevenLabs returned invalid conversation details")
        raw_data = payload.get("data")
        details = raw_data if isinstance(raw_data, dict) else payload
        returned_id = details.get("conversation_id")
        if returned_id != safe_id:
            raise ProviderRequestError("ElevenLabs returned mismatched conversation details")
        agent_id = details.get("agent_id")
        status = details.get("status")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ProviderRequestError("ElevenLabs conversation omitted agent_id")
        if status not in {"initiated", "in-progress", "processing", "done", "failed"}:
            raise ProviderRequestError("ElevenLabs conversation returned an invalid status")
        completed_event = None
        if status == "done":
            completed_event = parse_post_call_transcription(
                {"data": details},
                self._clock(),
            )
        return ConversationRepairSnapshot(
            conversation_id=safe_id,
            agent_id=agent_id.strip(),
            status=status,
            has_audio=details.get("has_audio") is True,
            completed_event=completed_event,
        )


def _conversation_id(value: str) -> str:
    if not isinstance(value, str) or CONVERSATION_ID_PATTERN.fullmatch(value) is None:
        raise ProviderRequestError("Invalid ElevenLabs conversation identifier")
    return value
