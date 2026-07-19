"""Read-only operator boundaries for recording playback and webhook repair."""

from __future__ import annotations

import hashlib
import hmac
from typing import Literal, Protocol, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from services.api.app.contracts import CallRecord
from services.api.app.core.errors import (
    DomainConflict,
    ProviderConfigurationError,
    ProviderRequestError,
    ResourceNotFound,
    WebhookAuthenticationError,
)
from services.api.app.integrations.elevenlabs.conversations import (
    ConversationRepairSnapshot,
)
from services.api.app.integrations.elevenlabs.models import (
    VerifiedPostCallTranscription,
)
from services.api.app.integrations.elevenlabs.recordings import (
    ALLOWED_AUDIO_TYPES,
    MAX_RECORDING_BYTES,
    RecordingAudio,
)
from services.api.app.orchestration.models import CallAttempt
from services.api.app.orchestration.recording_capability import (
    RecordingCapabilitySigner,
)

MIN_OPERATOR_SECRET_CHARACTERS = 32


class LiveVoiceCallLookup(Protocol):
    """Read-only call state required by the operator boundary."""

    def list_calls(self, job_id: UUID) -> list[CallRecord]: ...

    def get_attempt(self, call_id: UUID) -> CallAttempt | None: ...


class ConversationRepairClient(Protocol):
    def fetch_for_repair(self, conversation_id: str) -> ConversationRepairSnapshot: ...


class RecordingClient(Protocol):
    def fetch_audio(
        self,
        conversation_id: str,
        *,
        has_audio: bool,
    ) -> RecordingAudio: ...


class RecordingProxyPayload(BaseModel):
    """Validated transient bytes and response metadata; never persisted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: bytes = Field(min_length=1, max_length=MAX_RECORDING_BYTES)
    media_type: str
    content_length: int = Field(gt=0, le=MAX_RECORDING_BYTES)
    cache_control: Literal["no-store"] = "no-store"


class CompletedConversationRepairInput(BaseModel):
    """Transient input passed unchanged to the existing canonical materializer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["done"] = "done"
    attempt: CallAttempt
    event: VerifiedPostCallTranscription


class FailedConversationRepairInput(BaseModel):
    """Minimal failed-provider input for the canonical failure write boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["failed"] = "failed"
    attempt: CallAttempt
    idempotency_key: str = Field(min_length=1, max_length=200)
    failure_code: Literal["provider_conversation_failed"] = (
        "provider_conversation_failed"
    )


ConversationRepairInput: TypeAlias = (
    CompletedConversationRepairInput | FailedConversationRepairInput
)


class LiveVoiceOperatorService:
    """Authorize repair and proxy reads without mutating canonical state."""

    def __init__(
        self,
        *,
        calls: LiveVoiceCallLookup,
        signer: RecordingCapabilitySigner,
        conversations: ConversationRepairClient,
        recordings: RecordingClient,
        operator_secret: str,
    ) -> None:
        if (
            not isinstance(operator_secret, str)
            or len(operator_secret) < MIN_OPERATOR_SECRET_CHARACTERS
        ):
            raise ProviderConfigurationError(
                "VOICE_OPERATOR_SECRET must contain at least 32 characters"
            )
        self._calls = calls
        self._signer = signer
        self._conversations = conversations
        self._recordings = recordings
        self._operator_secret = operator_secret

    def fetch_recording(
        self,
        call_id: UUID,
        job_id: UUID,
        signature: str,
    ) -> RecordingProxyPayload:
        """Resolve and fetch audio only after capability and canonical-state checks."""

        self._signer.verify(call_id, job_id, signature)
        canonical_call = next(
            (
                call
                for call in self._calls.list_calls(job_id)
                if call.call_id == call_id
            ),
            None,
        )
        expected_url = self._signer.build_url(call_id, job_id)
        if (
            canonical_call is None
            or canonical_call.recording_url is None
            or str(canonical_call.recording_url) != str(expected_url)
        ):
            raise ResourceNotFound("Canonical call recording was not found")
        attempt = self._attempt(call_id, expected_job_id=job_id)
        reference = attempt.reference
        assert reference is not None
        snapshot = self._conversations.fetch_for_repair(reference.conversation_id)
        self._validate_snapshot(snapshot, attempt)
        if snapshot.status != "done":
            raise DomainConflict("Provider recording is not ready")
        if not snapshot.has_audio:
            raise ResourceNotFound("Provider conversation has no saved recording")
        audio = self._recordings.fetch_audio(
            reference.conversation_id,
            has_audio=True,
        )
        self._validate_audio(audio)
        return RecordingProxyPayload(
            content=audio.content,
            media_type=audio.media_type,
            content_length=len(audio.content),
        )

    def prepare_repair(
        self,
        call_id: UUID,
        supplied_operator_secret: str | None,
    ) -> ConversationRepairInput:
        """Return typed transient input; canonicalization remains a separate boundary."""

        supplied = (
            supplied_operator_secret
            if isinstance(supplied_operator_secret, str)
            else ""
        )
        if not hmac.compare_digest(
            self._operator_secret.encode("utf-8"),
            supplied.encode("utf-8"),
        ):
            raise WebhookAuthenticationError("Invalid operator authorization")
        attempt = self._attempt(call_id)
        reference = attempt.reference
        assert reference is not None
        snapshot = self._conversations.fetch_for_repair(reference.conversation_id)
        self._validate_snapshot(snapshot, attempt)
        if snapshot.status == "done":
            event = snapshot.completed_event
            if event is None:
                raise ProviderRequestError(
                    "Completed provider conversation omitted repair data"
                )
            if (
                event.conversation_id != reference.conversation_id
                or event.agent_id != attempt.expected_agent_id
            ):
                raise DomainConflict("Provider repair event correlation mismatch")
            return CompletedConversationRepairInput(
                attempt=attempt,
                event=event.model_copy(
                    update={
                        "idempotency_key": _repair_idempotency_key(
                            "post_call_transcription",
                            reference.conversation_id,
                        )
                    },
                    deep=True,
                ),
            )
        if snapshot.status == "failed":
            return FailedConversationRepairInput(
                attempt=attempt,
                idempotency_key=_repair_idempotency_key(
                    "provider_conversation_failed",
                    reference.conversation_id,
                ),
            )
        raise DomainConflict("Provider conversation is not repairable yet")

    def _attempt(
        self,
        call_id: UUID,
        *,
        expected_job_id: UUID | None = None,
    ) -> CallAttempt:
        attempt = self._calls.get_attempt(call_id)
        if (
            attempt is None
            or attempt.reference is None
            or (expected_job_id is not None and attempt.job_id != expected_job_id)
        ):
            raise ResourceNotFound("Call attempt conversation was not found")
        return attempt

    @staticmethod
    def _validate_snapshot(
        snapshot: ConversationRepairSnapshot,
        attempt: CallAttempt,
    ) -> None:
        reference = attempt.reference
        assert reference is not None
        if (
            snapshot.conversation_id != reference.conversation_id
            or snapshot.agent_id != attempt.expected_agent_id
        ):
            raise DomainConflict("Provider conversation correlation mismatch")

    @staticmethod
    def _validate_audio(audio: RecordingAudio) -> None:
        if audio.media_type not in ALLOWED_AUDIO_TYPES:
            raise ProviderRequestError("Provider returned unsupported recording audio")
        if not audio.content:
            raise ResourceNotFound("Provider recording was empty")
        if len(audio.content) > MAX_RECORDING_BYTES:
            raise ProviderRequestError("Provider recording exceeded the size limit")


def _repair_idempotency_key(event_type: str, conversation_id: str) -> str:
    """Keep operator repair replay-stable even when provider details omit event time."""

    material = f"veramove-repair:{event_type}:{conversation_id}".encode()
    return hashlib.sha256(material).hexdigest()
