"""Authenticate ElevenLabs webhook bytes and normalize only safe event fields."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from services.api.app.contracts import CallStatus
from services.api.app.core.errors import (
    WebhookAuthenticationError,
    WebhookPayloadError,
)
from services.api.app.integrations.elevenlabs.analysis import (
    parse_call_initiation_failure,
    parse_post_call_transcription,
)
from services.api.app.integrations.elevenlabs.models import VerifiedElevenLabsEvent
from services.api.app.orchestration.models import NormalizedVoiceEvent

MAX_PROVIDER_BODY_BYTES = 2_000_000


def utc_now() -> datetime:
    """Return the current UTC time for signature freshness checks."""

    return datetime.now(UTC)


class ElevenLabsWebhookProcessor:
    """Verify raw requests before parsing and discard sensitive provider fields."""

    def __init__(
        self,
        secret: str | None,
        clock: Callable[[], datetime] = utc_now,
        tolerance_seconds: int = 300,
    ) -> None:
        self._secret = secret
        self._clock = clock
        self._tolerance_seconds = tolerance_seconds

    def process(
        self,
        raw_body: bytes,
        signature_header: str | None,
    ) -> NormalizedVoiceEvent:
        """Authenticate bytes, then parse and reduce the event to an allowlist."""

        verified_timestamp = self._verify(raw_body, signature_header)
        payload = self._parse_object(raw_body)
        return self._normalize(payload, verified_timestamp)

    def process_provider_event(
        self,
        raw_body: bytes,
        signature_header: str | None,
    ) -> VerifiedElevenLabsEvent:
        """Authenticate and parse a bounded provider event for canonicalization."""

        verified_timestamp = self._verify(raw_body, signature_header)
        if len(raw_body) > MAX_PROVIDER_BODY_BYTES:
            raise WebhookPayloadError("ElevenLabs webhook body is too large")
        payload = self._parse_object(raw_body)
        event_type = payload.get("type")
        event_timestamp = self._event_timestamp(
            payload.get("event_timestamp"),
            verified_timestamp,
        )
        if event_type == "post_call_transcription":
            return parse_post_call_transcription(payload, event_timestamp)
        if event_type == "call_initiation_failure":
            return parse_call_initiation_failure(payload, event_timestamp)
        raise WebhookPayloadError("ElevenLabs webhook event type is unsupported")

    def _verify(self, raw_body: bytes, signature_header: str | None) -> int:
        if not self._secret:
            raise WebhookAuthenticationError("ElevenLabs webhook authentication is not configured")
        if not signature_header:
            raise WebhookAuthenticationError("Missing ElevenLabs signature")
        try:
            parts = dict(item.split("=", 1) for item in signature_header.split(","))
            timestamp = int(parts["t"])
            supplied = parts["v0"]
        except (KeyError, TypeError, ValueError):
            raise WebhookAuthenticationError("Malformed ElevenLabs signature") from None
        now = int(self._clock().timestamp())
        if abs(now - timestamp) > self._tolerance_seconds:
            raise WebhookAuthenticationError("ElevenLabs webhook timestamp is stale")
        signed = str(timestamp).encode("ascii") + b"." + raw_body
        expected = hmac.new(
            self._secret.encode(),
            signed,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, supplied):
            raise WebhookAuthenticationError("Invalid ElevenLabs signature")
        return timestamp

    @staticmethod
    def _parse_object(raw_body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise WebhookPayloadError("ElevenLabs webhook body must be valid JSON") from None
        if not isinstance(payload, dict):
            raise WebhookPayloadError("ElevenLabs webhook body must be a JSON object")
        return payload

    def _normalize(
        self,
        payload: dict[str, Any],
        verified_timestamp: int,
    ) -> NormalizedVoiceEvent:
        data = payload.get("data")
        provider_data = data if isinstance(data, dict) else {}
        event_type = payload.get("type") or payload.get("event_type")
        if not isinstance(event_type, str) or not event_type.strip():
            raise WebhookPayloadError("ElevenLabs webhook event type is missing")

        conversation_id = self._optional_text(
            provider_data.get("conversation_id", payload.get("conversation_id")),
            "conversation_id",
        )
        provider_status = self._optional_text(
            provider_data.get("status", payload.get("status")),
            "status",
        )
        call_id = self._optional_uuid(provider_data.get("call_id", payload.get("call_id")))
        event_timestamp = self._event_timestamp(
            payload.get("event_timestamp"),
            verified_timestamp,
        )
        call_status = {
            "done": CallStatus.COMPLETED,
            "failed": CallStatus.FAILED,
        }.get(provider_status)

        explicit_key = payload.get("idempotency_key")
        if explicit_key is not None:
            if not isinstance(explicit_key, str) or not explicit_key.strip():
                raise WebhookPayloadError("ElevenLabs webhook idempotency key is invalid")
            idempotency_key = explicit_key.strip()
        else:
            replay_material = (
                f"{event_type.strip()}:{conversation_id or ''}:{event_timestamp.isoformat()}"
            )
            idempotency_key = hashlib.sha256(replay_material.encode()).hexdigest()

        try:
            return NormalizedVoiceEvent(
                idempotency_key=idempotency_key,
                event_type=event_type.strip(),
                event_timestamp=event_timestamp,
                conversation_id=conversation_id,
                call_id=call_id,
                call_status=call_status,
                provider_status=provider_status,
            )
        except ValidationError as exc:
            raise WebhookPayloadError("ElevenLabs webhook fields are invalid") from exc

    @staticmethod
    def _event_timestamp(value: Any, verified_timestamp: int) -> datetime:
        if value is None:
            return datetime.fromtimestamp(verified_timestamp, UTC)
        if isinstance(value, bool):
            raise WebhookPayloadError("ElevenLabs webhook event timestamp is invalid")
        if isinstance(value, int | float):
            try:
                return datetime.fromtimestamp(value, UTC)
            except (OverflowError, OSError, ValueError):
                pass
        elif isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError
                return parsed.astimezone(UTC)
            except ValueError:
                pass
        raise WebhookPayloadError("ElevenLabs webhook event timestamp is invalid")

    @staticmethod
    def _optional_text(value: Any, field_name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise WebhookPayloadError(f"ElevenLabs webhook {field_name} is invalid")
        return value.strip()

    @staticmethod
    def _optional_uuid(value: Any) -> UUID | None:
        if value is None:
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            raise WebhookPayloadError("ElevenLabs webhook call_id is invalid") from None
