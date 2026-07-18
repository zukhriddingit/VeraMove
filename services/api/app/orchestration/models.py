"""Internal orchestration models that do not weaken canonical completed-call contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from services.api.app.contracts import (
    CallOutcome,
    CallStatus,
    JobSpecV1,
    Vendor,
)


class CallKind(StrEnum):
    """Purpose of an outbound voice call."""

    QUOTE = "quote"
    NEGOTIATION = "negotiation"


class VoiceCallReference(BaseModel):
    """Provider identifiers returned after a call is accepted."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=200)
    provider_call_id: str = Field(min_length=1, max_length=200)


class CallAttempt(BaseModel):
    """Pending or in-progress call state kept outside the canonical aggregate."""

    model_config = ConfigDict(extra="forbid")

    call_id: UUID
    job_id: UUID
    kind: CallKind
    vendor: Vendor
    job_spec_snapshot: JobSpecV1
    status: CallStatus
    started_at: datetime
    completed_at: datetime | None = None
    reference: VoiceCallReference | None = None


class VoiceCallResult(BaseModel):
    """Provider-neutral result from initiating or completing a voice call."""

    model_config = ConfigDict(extra="forbid")

    reference: VoiceCallReference
    outcome: CallOutcome | None = None
    recording_url: HttpUrl | None = None
    completed_at: datetime | None = None


class JobEvent(BaseModel):
    """Safe provider-neutral event exposed by orchestration."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    call_id: UUID | None = None
    event_type: str = Field(min_length=1, max_length=120)
    occurred_at: datetime
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class NormalizedVoiceEvent(BaseModel):
    """Authenticated provider event stripped of transcript and arbitrary metadata."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=120)
    event_timestamp: datetime
    conversation_id: str | None = Field(default=None, max_length=200)
    call_id: UUID | None = None
    call_status: CallStatus | None = None
    provider_status: str | None = Field(default=None, max_length=80)
