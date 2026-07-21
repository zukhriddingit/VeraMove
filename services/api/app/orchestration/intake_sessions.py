"""Safe correlation state for web and ElevenLabs voice-intake sessions."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from services.api.app.contracts import (
    DataClassification,
    IntakeSource,
    JobRecord,
    JobSpecV1,
    JobState,
)
from services.api.app.core.errors import (
    DomainConflict,
    ResourceNotFound,
    WebhookAuthenticationError,
    WebhookPayloadError,
)


class IntakeDataMode(StrEnum):
    """Explicit privacy boundary selected before starting a browser interview."""

    SUPERVISED_ROLE_PLAY = "supervised_role_play"
    REAL_REDACTED = "real_redacted"


class IntakeRecoveryAction(StrEnum):
    """The one terminal action claimed by an incomplete intake."""

    RESUME = "resume"
    MANUAL = "manual"


class IntakeSessionStatus(StrEnum):
    """Lifecycle of provider correlation before a normal JobRecord exists."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    INCOMPLETE = "incomplete"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_INTAKE_STATUSES = frozenset(
    {
        IntakeSessionStatus.INCOMPLETE,
        IntakeSessionStatus.COMPLETED,
        IntakeSessionStatus.FAILED,
    }
)


class IntakeSession(BaseModel):
    """Internal non-PII provider correlation; never stores a transcript or phone."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    intake_session_id: UUID = Field(default_factory=uuid4)
    job_id: UUID = Field(default_factory=uuid4)
    provider_call_key_hash: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    expected_agent_id: str = Field(min_length=1, max_length=200)
    agent_config_version: str = Field(min_length=1, max_length=80)
    data_mode: IntakeDataMode = IntakeDataMode.SUPERVISED_ROLE_PLAY
    status: IntakeSessionStatus = IntakeSessionStatus.PENDING
    conversation_id: str | None = Field(default=None, min_length=1, max_length=200)
    partial_job_spec: JobSpecV1 | None = None
    base_job_spec: JobSpecV1 | None = None
    missing_fields: tuple[str, ...] = Field(default=(), max_length=40)
    terminal_reason: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_]+$",
        max_length=80,
    )
    recovery_action: IntakeRecoveryAction | None = None
    recovery_target_id: UUID | None = None
    resumed_from_session_id: UUID | None = None
    failure_code: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_]+$",
        max_length=80,
    )
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    browser_credential_issued_at: datetime | None = None

    @field_validator(
        "created_at",
        "updated_at",
        "completed_at",
        "browser_credential_issued_at",
    )
    @classmethod
    def timestamps_are_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("intake session timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def status_matches_correlation(self) -> IntakeSession:
        if self.updated_at < self.created_at:
            raise ValueError("intake session update cannot precede creation")
        if (
            self.status
            in {
                IntakeSessionStatus.IN_PROGRESS,
                IntakeSessionStatus.INCOMPLETE,
                IntakeSessionStatus.COMPLETED,
            }
            and self.conversation_id is None
        ):
            raise ValueError("active or completed intake sessions require a conversation ID")
        if (self.status is IntakeSessionStatus.COMPLETED) != (self.completed_at is not None):
            raise ValueError("completed intake sessions require completed_at")
        if self.status is not IntakeSessionStatus.FAILED and self.failure_code is not None:
            raise ValueError("failure_code requires a failed intake session")
        if self.status is IntakeSessionStatus.FAILED and self.failure_code is None:
            raise ValueError("failed intake sessions require failure_code")
        if self.status is IntakeSessionStatus.INCOMPLETE:
            if self.partial_job_spec is None:
                raise ValueError("incomplete intake sessions require partial_job_spec")
            expected_missing = tuple(self.partial_job_spec.missing_required_fields())
            if self.missing_fields != expected_missing:
                raise ValueError("missing_fields must match partial_job_spec")
            if self.terminal_reason is None:
                raise ValueError("incomplete intake sessions require terminal_reason")
        elif (
            self.partial_job_spec is not None
            or self.missing_fields
            or self.terminal_reason is not None
        ):
            raise ValueError("partial intake fields require an incomplete session")
        expected_classification = _classification_for_mode(self.data_mode)
        for field_name, snapshot in (
            ("partial_job_spec", self.partial_job_spec),
            ("base_job_spec", self.base_job_spec),
        ):
            if snapshot is None:
                continue
            if snapshot.job_id != self.job_id:
                raise ValueError(f"{field_name} must use the intake session job_id")
            if snapshot.confirmed or snapshot.confirmed_at or snapshot.locked_version:
                raise ValueError(f"{field_name} must remain unlocked")
            if snapshot.intake_source is not IntakeSource.VOICE:
                raise ValueError(f"{field_name} must use voice intake source")
            if snapshot.data_classification is not expected_classification:
                raise ValueError(f"{field_name} must match intake data_mode")
        if (self.base_job_spec is None) != (self.resumed_from_session_id is None):
            raise ValueError(
                "base_job_spec and resumed_from_session_id must be set together"
            )
        if self.recovery_action is None and self.recovery_target_id is not None:
            raise ValueError("recovery_target_id requires recovery_action")
        if self.recovery_action is not None:
            if self.status is not IntakeSessionStatus.INCOMPLETE:
                raise ValueError("recovery_action requires an incomplete intake session")
            if self.recovery_target_id is None:
                raise ValueError("recovery_action requires recovery_target_id")
        if (
            self.browser_credential_issued_at is not None
            and self.browser_credential_issued_at < self.created_at
        ):
            raise ValueError("browser credential reservation cannot precede session creation")
        if (
            self.browser_credential_issued_at is not None
            and self.provider_call_key_hash is not None
        ):
            raise ValueError("telephone intake sessions cannot reserve browser credentials")
        return self


class IntakeSessionView(BaseModel):
    """Safe orchestration view returned through the typed API boundary."""

    model_config = ConfigDict(extra="forbid")

    intake_session_id: UUID
    job_id: UUID
    data_mode: IntakeDataMode
    status: IntakeSessionStatus
    conversation_id: str | None = None
    job_spec: JobSpecV1 | None = None
    partial_job_spec: JobSpecV1 | None = None
    missing_fields: tuple[str, ...] = ()
    terminal_reason: str | None = None
    recovery_action: IntakeRecoveryAction | None = None
    recovery_target_id: UUID | None = None
    resumed_from_session_id: UUID | None = None
    recovery_available: bool = False


class IntakeSessionStore(Protocol):
    """Minimal combined repository surface used by the intake-session service."""

    def create_intake_session(self, session: IntakeSession) -> IntakeSession: ...

    def get_intake_session(self, session_id: UUID) -> IntakeSession | None: ...

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

    def get(self, job_id: UUID) -> JobRecord | None: ...


_ALLOWED_TRANSITIONS = {
    IntakeSessionStatus.PENDING: frozenset(
        {
            IntakeSessionStatus.PENDING,
            IntakeSessionStatus.IN_PROGRESS,
            IntakeSessionStatus.INCOMPLETE,
            IntakeSessionStatus.COMPLETED,
            IntakeSessionStatus.FAILED,
        }
    ),
    IntakeSessionStatus.IN_PROGRESS: frozenset(
        {
            IntakeSessionStatus.IN_PROGRESS,
            IntakeSessionStatus.INCOMPLETE,
            IntakeSessionStatus.COMPLETED,
            IntakeSessionStatus.FAILED,
        }
    ),
    IntakeSessionStatus.INCOMPLETE: frozenset({IntakeSessionStatus.INCOMPLETE}),
    IntakeSessionStatus.COMPLETED: frozenset({IntakeSessionStatus.COMPLETED}),
    IntakeSessionStatus.FAILED: frozenset({IntakeSessionStatus.FAILED}),
}


def utc_now() -> datetime:
    """Return an aware timestamp without tying the model to a provider clock."""

    return datetime.now(UTC)


def provider_call_key_hash(provider_call_key: str) -> str:
    """Hash a bounded opaque provider key so the original value is never persisted."""

    normalized = _bounded_text(provider_call_key, "call_sid", max_length=200)
    material = f"elevenlabs:intake:{normalized}".encode()
    return hashlib.sha256(material).hexdigest()


def verify_pre_call_secret(expected: str | None, supplied: str | None) -> None:
    """Authenticate before request bytes are read or parsed."""

    if expected is None or supplied is None or not hmac.compare_digest(expected, supplied):
        raise WebhookAuthenticationError("Invalid ElevenLabs conversation-initiation secret")


def validate_intake_session_update(
    current: IntakeSession,
    candidate: IntakeSession,
) -> None:
    """Enforce immutable correlation identity and one-way terminal transitions."""

    immutable_fields = (
        "intake_session_id",
        "job_id",
        "provider_call_key_hash",
        "expected_agent_id",
        "agent_config_version",
        "data_mode",
        "base_job_spec",
        "resumed_from_session_id",
        "created_at",
    )
    if any(getattr(current, name) != getattr(candidate, name) for name in immutable_fields):
        if current.data_mode != candidate.data_mode:
            raise DomainConflict("Intake session intake mode cannot be changed")
        raise DomainConflict("Intake session identity cannot be changed")
    if candidate.status not in _ALLOWED_TRANSITIONS[current.status]:
        raise DomainConflict("Intake session terminal state cannot be changed")
    if current.conversation_id is not None and candidate.conversation_id != current.conversation_id:
        raise DomainConflict("Intake session conversation identity cannot be changed")
    if (
        current.browser_credential_issued_at is not None
        and candidate.browser_credential_issued_at
        != current.browser_credential_issued_at
    ):
        raise DomainConflict("Intake session credential reservation cannot be changed")
    if candidate.updated_at < current.updated_at:
        raise DomainConflict("Intake session updated_at cannot move backwards")
    if current.partial_job_spec is not None and (
        candidate.partial_job_spec != current.partial_job_spec
        or candidate.missing_fields != current.missing_fields
        or candidate.terminal_reason != current.terminal_reason
    ):
        raise DomainConflict("Incomplete intake snapshot cannot be changed")
    if current.recovery_action is not None and (
        candidate.recovery_action != current.recovery_action
        or candidate.recovery_target_id != current.recovery_target_id
    ):
        raise DomainConflict("Incomplete intake recovery action cannot be changed")


class IntakeSessionService:
    """Create and resolve idempotent intake sessions without persisting provider PII."""

    def __init__(
        self,
        repository: IntakeSessionStore,
        expected_agent_id: str,
        agent_config_version: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repository = repository
        self.expected_agent_id = _bounded_text(
            expected_agent_id,
            "expected intake agent ID",
            max_length=200,
        )
        self.agent_config_version = _bounded_text(
            agent_config_version,
            "agent config version",
            max_length=80,
        )
        self.clock = clock

    def create_web_session(
        self,
        *,
        data_mode: IntakeDataMode = IntakeDataMode.SUPERVISED_ROLE_PLAY,
    ) -> IntakeSessionView:
        session = self._create_session(
            provider_key_hash=None,
            data_mode=data_mode,
        )
        return self._view(session)

    def reserve_browser_credential(self, session_id: UUID | str) -> IntakeSession:
        session = self._require_session(UUID(str(session_id)))
        return self.repository.reserve_intake_browser_credential(
            session.intake_session_id,
            self.clock(),
        )

    def create_pre_call_session(
        self,
        *,
        agent_id: str,
        provider_call_key: str,
    ) -> IntakeSession:
        normalized_agent_id = _bounded_text(agent_id, "agent_id", max_length=200)
        if not hmac.compare_digest(normalized_agent_id, self.expected_agent_id):
            raise WebhookPayloadError("Unexpected ElevenLabs intake agent")
        return self._create_session(
            provider_key_hash=provider_call_key_hash(provider_call_key),
            data_mode=IntakeDataMode.SUPERVISED_ROLE_PLAY,
        )

    def get_session(self, session_id: UUID) -> IntakeSessionView:
        session = self.repository.get_intake_session(session_id)
        if session is None:
            raise ResourceNotFound(f"Intake session {session_id} was not found")
        return self._view(session)

    def get_by_conversation(self, conversation_id: str) -> IntakeSessionView:
        normalized = _bounded_text(
            conversation_id,
            "conversation_id",
            max_length=200,
        )
        session = self.repository.find_intake_session_by_conversation_id(normalized)
        if session is None:
            raise ResourceNotFound(f"Intake conversation {normalized} was not found")
        return self._view(session)

    def attach_conversation(
        self,
        session_id: UUID | str,
        conversation_id: str,
        *,
        agent_id: str,
    ) -> IntakeSession:
        session = self._require_session(UUID(str(session_id)))
        normalized_agent_id = _bounded_text(agent_id, "agent_id", max_length=200)
        if not hmac.compare_digest(normalized_agent_id, session.expected_agent_id):
            raise WebhookPayloadError("Unexpected ElevenLabs intake agent")
        normalized_conversation = _bounded_text(
            conversation_id,
            "conversation_id",
            max_length=200,
        )
        if session.conversation_id == normalized_conversation and session.status in {
            IntakeSessionStatus.IN_PROGRESS,
            IntakeSessionStatus.INCOMPLETE,
            IntakeSessionStatus.COMPLETED,
        }:
            return session
        updated = session.model_copy(
            update={
                "conversation_id": normalized_conversation,
                "status": IntakeSessionStatus.IN_PROGRESS,
                "updated_at": self.clock(),
            },
            deep=True,
        )
        return self.repository.save_intake_session(updated)

    def complete_session(
        self,
        session_id: UUID | str,
        conversation_id: str,
    ) -> IntakeSession:
        session = self._require_session(UUID(str(session_id)))
        normalized_conversation = _bounded_text(
            conversation_id,
            "conversation_id",
            max_length=200,
        )
        if session.status is IntakeSessionStatus.COMPLETED:
            if session.conversation_id != normalized_conversation:
                raise DomainConflict("Intake session conversation identity cannot be changed")
            return session
        record = self.repository.get(session.job_id)
        self._validate_completed_job(session, record)
        completed_at = self.clock()
        updated = session.model_copy(
            update={
                "conversation_id": normalized_conversation,
                "status": IntakeSessionStatus.COMPLETED,
                "updated_at": completed_at,
                "completed_at": completed_at,
            },
            deep=True,
        )
        return self.repository.save_intake_session(updated)

    def fail_session(
        self,
        session_id: UUID | str,
        failure_code: str = "intake_failed",
    ) -> IntakeSession:
        session = self._require_session(UUID(str(session_id)))
        if session.status is IntakeSessionStatus.FAILED:
            return session
        normalized_failure = _bounded_text(
            failure_code,
            "failure_code",
            max_length=80,
        )
        updated = session.model_copy(
            update={
                "status": IntakeSessionStatus.FAILED,
                "failure_code": normalized_failure,
                "updated_at": self.clock(),
            },
            deep=True,
        )
        return self.repository.save_intake_session(updated)

    def _create_session(
        self,
        provider_key_hash: str | None,
        *,
        data_mode: IntakeDataMode,
    ) -> IntakeSession:
        now = self.clock()
        candidate = IntakeSession(
            expected_agent_id=self.expected_agent_id,
            agent_config_version=self.agent_config_version,
            provider_call_key_hash=provider_key_hash,
            data_mode=data_mode,
            created_at=now,
            updated_at=now,
        )
        return self.repository.create_intake_session(candidate)

    def _require_session(self, session_id: UUID) -> IntakeSession:
        session = self.repository.get_intake_session(session_id)
        if session is None:
            raise ResourceNotFound(f"Intake session {session_id} was not found")
        return session

    def _view(self, session: IntakeSession) -> IntakeSessionView:
        record = self.repository.get(session.job_id)
        if session.status is IntakeSessionStatus.COMPLETED:
            self._validate_completed_job(session, record)
            assert record is not None
            job_spec = record.job_spec
        else:
            if record is not None:
                raise DomainConflict("Incomplete intake session cannot own a JobRecord")
            job_spec = None
        return IntakeSessionView(
            intake_session_id=session.intake_session_id,
            job_id=session.job_id,
            data_mode=session.data_mode,
            status=session.status,
            conversation_id=session.conversation_id,
            job_spec=job_spec,
            partial_job_spec=session.partial_job_spec or session.base_job_spec,
            missing_fields=(
                session.missing_fields
                if session.partial_job_spec is not None
                else tuple(session.base_job_spec.missing_required_fields())
                if session.base_job_spec is not None
                else ()
            ),
            terminal_reason=session.terminal_reason,
            recovery_action=session.recovery_action,
            recovery_target_id=session.recovery_target_id,
            resumed_from_session_id=session.resumed_from_session_id,
            recovery_available=(
                session.status is IntakeSessionStatus.INCOMPLETE
                and session.recovery_action is None
            ),
        )

    @staticmethod
    def _validate_completed_job(
        session: IntakeSession,
        record: JobRecord | None,
    ) -> None:
        if record is None or record.job_spec.job_id != session.job_id:
            raise DomainConflict("Completed intake session requires its canonical JobRecord")
        if (
            record.state is not JobState.INTAKE_COMPLETE
            or record.job_spec.intake_source is not IntakeSource.VOICE
            or record.job_spec.confirmed
            or record.job_spec.confirmed_at is not None
            or record.job_spec.locked_version is not None
        ):
            raise DomainConflict("Completed intake session requires an unconfirmed voice JobSpec")


def _bounded_text(value: str, field_name: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WebhookPayloadError(f"ElevenLabs {field_name} is missing or invalid")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise WebhookPayloadError(f"ElevenLabs {field_name} is too long")
    return normalized


def _classification_for_mode(mode: IntakeDataMode) -> DataClassification:
    if mode is IntakeDataMode.REAL_REDACTED:
        return DataClassification.REAL_REDACTED
    return DataClassification.ROLE_PLAY
