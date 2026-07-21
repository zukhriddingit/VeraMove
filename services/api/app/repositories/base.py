"""Persistence protocols and safe atomic voice materialization models."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from services.api.app.contracts import (
    CallRecord,
    IntakeSource,
    JobRecord,
    JobState,
    JobVendorResearchV1,
    QuoteV1,
    VendorCallAuthorizationV1,
    VendorSuppressionV1,
)
from services.api.app.orchestration.intake_sessions import (
    IntakeSession,
    IntakeSessionStatus,
)
from services.api.app.orchestration.models import CallAttempt, JobEvent

_FORBIDDEN_MATERIALIZATION_KEYS = frozenset(
    {
        "analysis",
        "api_key",
        "audio",
        "from_number",
        "phone",
        "phone_number",
        "raw_body",
        "raw_payload",
        "secret",
        "to_number",
        "transcript",
    }
)
_E164_IN_TEXT = re.compile(r"\+[1-9]\d{7,14}")


class VoiceWebhookLease(BaseModel):
    """Validated compare-and-set inputs for one bounded receipt lease."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    idempotency_key: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=120)
    lease_token: UUID
    lease_expires_at: datetime
    now: datetime

    @model_validator(mode="after")
    def validate_times(self) -> VoiceWebhookLease:
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.lease_expires_at, self.now)
        ):
            raise ValueError("Voice webhook lease timestamps must include a timezone")
        if self.lease_expires_at <= self.now:
            raise ValueError("Voice webhook lease must expire in the future")
        return self


class VoiceWebhookClaimResult(BaseModel):
    """Receipt state returned without exposing lease-owner details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claimed: bool
    processed: bool

    @model_validator(mode="after")
    def processed_is_not_claimed(self) -> VoiceWebhookClaimResult:
        if self.claimed and self.processed:
            raise ValueError("Processed voice receipts cannot be claimed")
        return self


class VoiceWebhookFailureResult(BaseModel):
    """Safe acknowledgement for a compare-and-set receipt failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    failed: Literal[True] = True
    retryable: bool


class VoiceWebhookFailure(BaseModel):
    """Validated compare-and-set inputs for marking one receipt failed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    idempotency_key: str = Field(min_length=1, max_length=200)
    lease_token: UUID
    failure_code: str = Field(pattern=r"^[a-z0-9_:-]{1,80}$")
    retryable: bool
    now: datetime

    @model_validator(mode="after")
    def now_is_aware(self) -> VoiceWebhookFailure:
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("Voice webhook failure timestamp must include a timezone")
        return self


class VoiceWebhookFinalizeResult(BaseModel):
    """Exactly-once finalization acknowledgement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    processed: Literal[True] = True
    duplicate: bool


class VoiceIntakeCompletion(BaseModel):
    """Canonical values for completing one correlated voice-intake session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["completed"] = "completed"
    session: IntakeSession
    job: JobRecord
    event: JobEvent

    @model_validator(mode="after")
    def validate_completion(self) -> VoiceIntakeCompletion:
        if self.session.status is not IntakeSessionStatus.COMPLETED:
            raise ValueError("Voice intake completion requires a completed session")
        if self.session.conversation_id is None or self.session.failure_code is not None:
            raise ValueError("Voice intake completion session is not canonical")
        if (
            self.job.job_spec.job_id != self.session.job_id
            or self.event.job_id != self.session.job_id
            or self.event.call_id is not None
        ):
            raise ValueError("Voice intake completion identity does not match")
        if (
            self.job.state is not JobState.INTAKE_COMPLETE
            or self.job.job_spec.intake_source is not IntakeSource.VOICE
            or self.job.job_spec.confirmed
            or self.job.job_spec.confirmed_at is not None
            or self.job.job_spec.locked_version is not None
            or self.job.calls
            or self.job.quotes
        ):
            raise ValueError("Voice intake completion job is not canonical")
        if (
            self.session.completed_at != self.event.occurred_at
            or self.job.created_at != self.event.occurred_at
            or self.job.updated_at != self.event.occurred_at
        ):
            raise ValueError("Voice intake completion timestamps do not match")
        _assert_safe_materialization(self.model_dump(mode="json"))
        return self


class VoiceIntakeFailure(BaseModel):
    """Canonical values for one failed intake call before a JobRecord exists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["failed"] = "failed"
    session: IntakeSession
    event_type: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_failure(self) -> VoiceIntakeFailure:
        if (
            self.session.status is not IntakeSessionStatus.FAILED
            or self.session.failure_code is None
            or self.session.completed_at is not None
            or self.session.conversation_id is None
        ):
            raise ValueError("Voice intake failure requires a failed session")
        _assert_safe_materialization(self.model_dump(mode="json"))
        return self


class VoiceIntakeIncomplete(BaseModel):
    """Canonical structured-only result for an interview ended before confirmation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["incomplete"] = "incomplete"
    session: IntakeSession
    event_type: str = Field(min_length=1, max_length=120)

    @field_validator("session", mode="before")
    @classmethod
    def normalize_session(cls, value: Any) -> IntakeSession:
        if isinstance(value, IntakeSession):
            value = value.model_dump(mode="json")
        return IntakeSession.model_validate(value)

    @model_validator(mode="after")
    def validate_incomplete(self) -> VoiceIntakeIncomplete:
        if (
            self.session.status is not IntakeSessionStatus.INCOMPLETE
            or self.session.partial_job_spec is None
            or self.session.conversation_id is None
            or self.session.failure_code is not None
            or self.session.completed_at is not None
        ):
            raise ValueError("Voice intake incomplete session is not canonical")
        _assert_safe_materialization(self.model_dump(mode="json"))
        return self


VoiceIntakeMaterialization: TypeAlias = Annotated[
    VoiceIntakeCompletion | VoiceIntakeIncomplete | VoiceIntakeFailure,
    Field(discriminator="kind"),
]


class VoiceIntakeFinalizeRequest(BaseModel):
    """Validated compare-and-set request for one intake terminal transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    idempotency_key: str = Field(min_length=1, max_length=200)
    lease_token: UUID
    materialization: VoiceIntakeMaterialization
    now: datetime

    @model_validator(mode="after")
    def now_is_aware(self) -> VoiceIntakeFinalizeRequest:
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("Voice intake finalization timestamp must include a timezone")
        return self


class VoiceWebhookMaterialization(BaseModel):
    """Typed canonical values allowed to cross the atomic persistence boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt: CallAttempt
    call: CallRecord
    quote: QuoteV1 | None = None
    job: JobRecord
    event: JobEvent
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_canonical_identity_and_safety(self) -> VoiceWebhookMaterialization:
        if (
            self.attempt.call_id != self.call.call_id
            or self.attempt.job_id != self.call.job_id
            or self.attempt.vendor.vendor_id != self.call.vendor.vendor_id
            or self.job.job_spec.job_id != self.call.job_id
            or self.event.job_id != self.call.job_id
            or self.event.call_id != self.call.call_id
        ):
            raise ValueError("Voice materialization identity does not match")
        if (
            self.attempt.status != self.call.status
            or self.attempt.completed_at != self.call.completed_at
        ):
            raise ValueError("Voice materialization terminal state does not match")

        canonical_quote = self.call.outcome.quote
        if (canonical_quote is None) != (self.quote is None):
            raise ValueError("Voice materialization quote presence does not match call outcome")
        if self.quote is not None and self.quote != canonical_quote:
            raise ValueError("Voice materialization quote does not match call outcome")
        if not any(item.call_id == self.call.call_id for item in self.job.calls):
            raise ValueError("Voice materialization job must contain the canonical call")
        if self.quote is not None and not any(
            item.quote_id == self.quote.quote_id for item in self.job.quotes
        ):
            raise ValueError("Voice materialization job must contain the canonical quote")

        _assert_safe_materialization(self.model_dump(mode="json"))
        return self


class VoiceWebhookFinalizeRequest(BaseModel):
    """Validated compare-and-set inputs for one atomic canonical finalization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    idempotency_key: str = Field(min_length=1, max_length=200)
    lease_token: UUID
    materialization: VoiceWebhookMaterialization
    now: datetime

    @model_validator(mode="after")
    def now_is_aware(self) -> VoiceWebhookFinalizeRequest:
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("Voice webhook finalization timestamp must include a timezone")
        return self


def _assert_safe_materialization(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.casefold() in _FORBIDDEN_MATERIALIZATION_KEYS:
                raise ValueError("Voice materialization contains a forbidden field")
            _assert_safe_materialization(item)
        return
    if isinstance(value, list):
        for item in value:
            _assert_safe_materialization(item)
        return
    if isinstance(value, str) and _E164_IN_TEXT.search(value) is not None:
        raise ValueError("Voice materialization contains a phone-like value")


class JobRepository(Protocol):
    def create(self, record: JobRecord) -> JobRecord: ...

    def get(self, job_id: UUID) -> JobRecord | None: ...

    def save(self, record: JobRecord) -> JobRecord: ...

    def reset(self) -> None: ...


class CallRepository(Protocol):
    def create_attempt(self, attempt: CallAttempt) -> CallAttempt: ...

    def save_attempt(self, attempt: CallAttempt) -> CallAttempt: ...

    def get_attempt(self, call_id: UUID) -> CallAttempt | None: ...

    def list_attempts(self, job_id: UUID) -> list[CallAttempt]: ...

    def find_attempt_by_conversation_id(
        self,
        conversation_id: str,
    ) -> CallAttempt | None: ...

    def save_call(self, call: CallRecord) -> CallRecord: ...

    def list_calls(self, job_id: UUID) -> list[CallRecord]: ...

    def reserve_webhook(self, idempotency_key: str) -> bool: ...

    def claim_voice_webhook_receipt(
        self,
        lease: VoiceWebhookLease,
    ) -> VoiceWebhookClaimResult: ...

    def fail_voice_webhook_receipt(
        self,
        idempotency_key: str,
        lease_token: UUID,
        failure_code: str,
        retryable: bool,
        now: datetime,
    ) -> VoiceWebhookFailureResult: ...

    def finalize_voice_webhook(
        self,
        idempotency_key: str,
        lease_token: UUID,
        materialization: VoiceWebhookMaterialization,
        now: datetime,
    ) -> VoiceWebhookFinalizeResult: ...

    def finalize_voice_intake_webhook(
        self,
        idempotency_key: str,
        lease_token: UUID,
        materialization: VoiceIntakeMaterialization,
        now: datetime,
    ) -> VoiceWebhookFinalizeResult: ...

    def get_job_revision(self, job_id: UUID) -> int: ...

    def append_event(self, event: JobEvent) -> JobEvent: ...

    def list_events(self, job_id: UUID) -> list[JobEvent]: ...


class QuoteRepository(Protocol):
    def save_quote(self, quote: QuoteV1) -> QuoteV1: ...

    def list_quotes(self, job_id: UUID) -> list[QuoteV1]: ...

    def get_verified_competing_quote(
        self,
        job_id: UUID,
        target_vendor_id: UUID,
        job_spec_version: str,
    ) -> QuoteV1 | None: ...


class VendorResearchRepository(Protocol):
    """Research persistence isolated from call and quote aggregates."""

    def get_vendor_research(
        self,
        job_id: UUID,
        job_spec_version: str,
    ) -> JobVendorResearchV1 | None: ...

    def save_vendor_research(
        self,
        research: JobVendorResearchV1,
    ) -> JobVendorResearchV1: ...


class VendorCallAuthorizationRepository(Protocol):
    """Server-only consent and hashed suppression persistence."""

    def get_vendor_call_authorization(
        self,
        job_id: UUID,
        job_spec_version: str,
        vendor_id: UUID,
    ) -> VendorCallAuthorizationV1 | None: ...

    def list_vendor_call_authorizations(
        self,
        job_id: UUID,
        job_spec_version: str,
    ) -> list[VendorCallAuthorizationV1]: ...

    def save_vendor_call_authorization(
        self,
        authorization: VendorCallAuthorizationV1,
    ) -> VendorCallAuthorizationV1: ...

    def clear_vendor_call_authorizations(
        self,
        job_id: UUID,
        job_spec_version: str,
    ) -> None: ...

    def get_vendor_suppression(
        self,
        number_hash: str,
    ) -> VendorSuppressionV1 | None: ...

    def save_vendor_suppression(
        self,
        suppression: VendorSuppressionV1,
    ) -> VendorSuppressionV1: ...


class IntakeSessionRepository(Protocol):
    def create_intake_session(self, session: IntakeSession) -> IntakeSession: ...

    def get_intake_session(self, session_id: UUID) -> IntakeSession | None: ...

    def find_intake_session_by_provider_call_key_hash(
        self,
        provider_call_key_hash: str,
    ) -> IntakeSession | None: ...

    def find_intake_session_by_conversation_id(
        self,
        conversation_id: str,
    ) -> IntakeSession | None: ...

    def save_intake_session(self, session: IntakeSession) -> IntakeSession: ...

    def reserve_intake_browser_credential(
        self,
        session_id: UUID,
        issued_at: datetime,
    ) -> IntakeSession: ...

    def claim_intake_resume(
        self,
        session_id: UUID,
        child: IntakeSession,
        now: datetime,
    ) -> IntakeSession: ...

    def finish_intake_manually(
        self,
        session_id: UUID,
        job: JobRecord,
        now: datetime,
    ) -> JobRecord: ...


class VoiceMaterializationRepository(Protocol):
    """Narrow repository boundary used by asynchronous voice canonicalization."""

    def claim_voice_webhook_receipt(
        self,
        lease: VoiceWebhookLease,
    ) -> VoiceWebhookClaimResult: ...

    def fail_voice_webhook_receipt(
        self,
        idempotency_key: str,
        lease_token: UUID,
        failure_code: str,
        retryable: bool,
        now: datetime,
    ) -> VoiceWebhookFailureResult: ...

    def finalize_voice_webhook(
        self,
        idempotency_key: str,
        lease_token: UUID,
        materialization: VoiceWebhookMaterialization,
        now: datetime,
    ) -> VoiceWebhookFinalizeResult: ...

    def finalize_voice_intake_webhook(
        self,
        idempotency_key: str,
        lease_token: UUID,
        materialization: VoiceIntakeMaterialization,
        now: datetime,
    ) -> VoiceWebhookFinalizeResult: ...

    def get_job_revision(self, job_id: UUID) -> int: ...
