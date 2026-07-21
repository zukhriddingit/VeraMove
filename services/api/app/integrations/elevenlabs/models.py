"""Bounded provider-shaped models used only during ElevenLabs request handling."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from services.api.app.contracts import CallStatus

PrimitiveValue: TypeAlias = str | bool | int | float | None


class ElevenLabsDynamicVariables(BaseModel):
    """Allowlisted custom correlation variables echoed by ElevenLabs."""

    model_config = ConfigDict(extra="forbid", strict=True)

    job_id: UUID | None = None
    call_id: UUID | None = None
    intake_session_id: UUID | None = None
    vendor_id: UUID | None = None
    call_mode: Literal["quote", "negotiation"] | None = None
    call_context: Literal["supervised_role_play", "official_business"] | None = None
    job_spec_version: str | None = Field(default=None, max_length=20)
    agent_config_version: str | None = Field(default=None, max_length=80)
    job_spec_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )


class ElevenLabsTranscriptTurn(BaseModel):
    """One bounded transient transcript turn; tool metadata is never retained."""

    model_config = ConfigDict(extra="forbid", strict=True)

    role: str = Field(min_length=1, max_length=40)
    message: str | None = Field(default=None, max_length=2_000)
    time_in_call_secs: Decimal = Field(ge=0, decimal_places=3)


class VerifiedPostCallTranscription(BaseModel):
    """Authenticated post-call facts safe enough for transient canonicalization."""

    model_config = ConfigDict(extra="forbid", strict=True)

    idempotency_key: str = Field(min_length=1, max_length=200)
    event_type: Literal["post_call_transcription"] = "post_call_transcription"
    event_timestamp: datetime
    agent_id: str = Field(min_length=1, max_length=200)
    conversation_id: str = Field(min_length=1, max_length=200)
    provider_status: str = Field(min_length=1, max_length=80)
    call_status: CallStatus | None = None
    version_id: str | None = Field(default=None, max_length=200)
    environment: str | None = Field(default=None, max_length=80)
    has_audio: bool = False
    dynamic_variables: ElevenLabsDynamicVariables = Field(
        default_factory=ElevenLabsDynamicVariables
    )
    collected_data: dict[str, PrimitiveValue] = Field(default_factory=dict)
    transcript_turns: tuple[ElevenLabsTranscriptTurn, ...] = ()


class VerifiedCallInitiationFailure(BaseModel):
    """Authenticated failure event with all provider phone metadata discarded."""

    model_config = ConfigDict(extra="forbid", strict=True)

    idempotency_key: str = Field(min_length=1, max_length=200)
    event_type: Literal["call_initiation_failure"] = "call_initiation_failure"
    event_timestamp: datetime
    agent_id: str = Field(min_length=1, max_length=200)
    conversation_id: str = Field(min_length=1, max_length=200)
    failure_reason: Literal["busy", "no-answer", "unknown"]
    provider_status: Literal["failed"] = "failed"
    call_status: Literal[CallStatus.FAILED] = CallStatus.FAILED
    call_id: None = None


VerifiedElevenLabsEvent: TypeAlias = VerifiedPostCallTranscription | VerifiedCallInitiationFailure
