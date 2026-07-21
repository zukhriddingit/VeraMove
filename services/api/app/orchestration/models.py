"""Internal orchestration models that do not weaken canonical completed-call contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from services.api.app.contracts import (
    CallContext,
    CallOutcome,
    CallStatus,
    JobSpecV1,
    Vendor,
    VendorCallPlanV1,
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


def job_spec_sha256(job_spec: JobSpecV1) -> str:
    """Hash one canonical JSON representation of a locked JobSpec snapshot."""

    serialized = json.dumps(
        job_spec.model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class NegotiationContext(BaseModel):
    """Verified leverage identities captured before a negotiation call."""

    model_config = ConfigDict(extra="forbid")

    target_quote_id: UUID
    competitor_quote_id: UUID
    eligible_leverage_total: Decimal = Field(ge=0)
    evidence_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)


class CallAttempt(BaseModel):
    """Pending or in-progress call state kept outside the canonical aggregate."""

    model_config = ConfigDict(extra="forbid")

    call_id: UUID
    job_id: UUID
    kind: CallKind
    vendor: Vendor
    job_spec_snapshot: JobSpecV1
    job_spec_version: str = Field(min_length=1, max_length=20)
    job_spec_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    destination_slot: Literal[0, 1, 2] = 0
    expected_agent_id: str = Field(min_length=1, max_length=200)
    agent_config_version: str = Field(min_length=1, max_length=80)
    call_mode: Literal["quote", "negotiation"]
    negotiation_context: NegotiationContext | None = None
    status: CallStatus
    started_at: datetime
    completed_at: datetime | None = None
    reference: VoiceCallReference | None = None
    provider_version_id: str | None = Field(default=None, max_length=200)
    call_context: CallContext = CallContext.SUPERVISED_ROLE_PLAY
    authorization_id: UUID | None = None
    call_plan: VendorCallPlanV1 | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_audit_fields(cls, data: Any) -> Any:
        """Keep old synthetic constructors concise while deriving immutable audit facts."""

        if not isinstance(data, dict):
            return data
        values = dict(data)
        snapshot = values.get("job_spec_snapshot")
        if snapshot is not None:
            parsed = JobSpecV1.model_validate(snapshot)
            values.setdefault("job_spec_version", parsed.version)
            values.setdefault("job_spec_sha256", job_spec_sha256(parsed))
        raw_kind = values.get("kind")
        kind = raw_kind.value if isinstance(raw_kind, CallKind) else raw_kind
        values.setdefault("call_mode", kind)
        values.setdefault("expected_agent_id", "synthetic-mock-outbound-agent")
        values.setdefault("agent_config_version", "mock-v1")
        values.setdefault("call_context", CallContext.SUPERVISED_ROLE_PLAY)
        return values

    @model_validator(mode="after")
    def validate_audit_fields(self) -> CallAttempt:
        if self.job_spec_version != self.job_spec_snapshot.version:
            raise ValueError("Call attempt JobSpec version does not match snapshot")
        if self.job_spec_sha256 != job_spec_sha256(self.job_spec_snapshot):
            raise ValueError("Call attempt JobSpec hash does not match snapshot")
        if self.call_mode != self.kind.value:
            raise ValueError("Call attempt mode does not match kind")
        if self.kind is CallKind.QUOTE and self.negotiation_context is not None:
            raise ValueError("Quote attempts cannot contain negotiation context")
        if self.kind is CallKind.NEGOTIATION and self.negotiation_context is None:
            raise ValueError("Negotiation attempts require verified context")
        if self.call_context is CallContext.OFFICIAL_BUSINESS:
            if self.authorization_id is None:
                raise ValueError(
                    "official-business attempts require an authorization reference"
                )
            if self.call_plan is None:
                raise ValueError("official-business attempts require a vendor call plan")
        elif self.authorization_id is not None:
            raise ValueError(
                "role-play attempts cannot reference a vendor authorization"
            )
        if self.call_plan is not None and (
            self.call_plan.vendor_id != self.vendor.vendor_id
            or self.call_plan.job_spec_version != self.job_spec_version
            or self.call_plan.job_spec_sha256 != self.job_spec_sha256
        ):
            raise ValueError("call plan does not match the attempt snapshot")
        return self


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
