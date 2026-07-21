"""Bounded repair and one-action recovery for structured voice intake."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID, uuid4

from services.api.app.contracts import JobRecord, JobState, WebhookAck
from services.api.app.core.errors import (
    DomainConflict,
    ProviderConfigurationError,
    ProviderRequestError,
)
from services.api.app.integrations.elevenlabs.conversations import (
    ConversationRepairSnapshot,
)
from services.api.app.integrations.elevenlabs.models import (
    VerifiedPostCallTranscription,
)
from services.api.app.orchestration.intake_sessions import (
    TERMINAL_INTAKE_STATUSES,
    IntakeRecoveryAction,
    IntakeSession,
    IntakeSessionService,
    IntakeSessionStatus,
    IntakeSessionView,
)
from services.api.app.repositories.base import (
    IntakeSessionRepository,
    JobRepository,
)


class IntakeConversationRepairClient(Protocol):
    def fetch_for_repair(self, conversation_id: str) -> ConversationRepairSnapshot: ...


class IntakeEventMaterializer(Protocol):
    def materialize(self, event: VerifiedPostCallTranscription) -> WebhookAck: ...


class IntakeRecoveryRepository(IntakeSessionRepository, JobRepository, Protocol):
    """Atomic session/job operations needed by the recovery workflow."""


class IntakeRecoveryService:
    """Recover provider results or claim one structured continuation path."""

    def __init__(
        self,
        *,
        sessions: IntakeSessionService,
        repository: IntakeRecoveryRepository,
        conversations: IntakeConversationRepairClient | None,
        materializer: IntakeEventMaterializer | None,
        clock: Callable,
    ) -> None:
        self._sessions = sessions
        self._repository = repository
        self._conversations = conversations
        self._materializer = materializer
        self._clock = clock

    def recover(self, session_id: UUID) -> IntakeSessionView:
        session = self._sessions.require_session(session_id)
        if session.status in TERMINAL_INTAKE_STATUSES:
            return self._sessions.view_session(session)
        if session.conversation_id is None:
            raise DomainConflict("Intake session has no provider conversation")
        if self._conversations is None:
            raise ProviderConfigurationError(
                "Provider intake recovery is unavailable in this runtime"
            )
        snapshot = self._conversations.fetch_for_repair(session.conversation_id)
        self._validate_snapshot(snapshot, session)
        if snapshot.status == "failed":
            self._sessions.fail_session(session_id, "provider_conversation_failed")
            return self._sessions.get_session(session_id)
        if snapshot.status != "done":
            raise DomainConflict("Provider intake result is not ready")
        event = snapshot.completed_event
        if event is None:
            raise ProviderRequestError("Completed provider intake omitted repair data")
        self._validate_event(event, session)
        if self._materializer is None:
            raise ProviderConfigurationError(
                "Provider intake materialization is unavailable in this runtime"
            )
        self._materializer.materialize(event)
        result = self._sessions.get_session(session_id)
        if result.status not in TERMINAL_INTAKE_STATUSES:
            raise ProviderRequestError("Provider intake recovery did not reach a terminal state")
        return result

    def resume(self, session_id: UUID) -> IntakeSessionView:
        source = self._sessions.require_session(session_id)
        if source.status is not IntakeSessionStatus.INCOMPLETE:
            raise DomainConflict("Only incomplete intake sessions can continue speaking")
        if source.recovery_action is IntakeRecoveryAction.RESUME:
            assert source.recovery_target_id is not None
            return self._sessions.get_session(source.recovery_target_id)
        if source.recovery_action is not None:
            raise DomainConflict("Incomplete intake already has a recovery action")
        if source.partial_job_spec is None:
            raise DomainConflict("Incomplete intake has no structured partial spec")
        now = self._clock()
        child_job_id = uuid4()
        child = IntakeSession(
            job_id=child_job_id,
            expected_agent_id=source.expected_agent_id,
            agent_config_version=source.agent_config_version,
            data_mode=source.data_mode,
            base_job_spec=source.partial_job_spec.model_copy(
                update={"job_id": child_job_id},
                deep=True,
            ),
            resumed_from_session_id=source.intake_session_id,
            created_at=now,
            updated_at=now,
        )
        saved = self._repository.claim_intake_resume(session_id, child, now)
        return self._sessions.view_session(saved)

    def finish_manually(self, session_id: UUID) -> JobRecord:
        source = self._sessions.require_session(session_id)
        if source.status is not IntakeSessionStatus.INCOMPLETE:
            raise DomainConflict("Only incomplete intake sessions can finish manually")
        if source.recovery_action is IntakeRecoveryAction.MANUAL:
            assert source.recovery_target_id is not None
            existing = self._repository.get(source.recovery_target_id)
            if existing is None:
                raise DomainConflict("Manual intake recovery job is missing")
            return existing
        if source.recovery_action is not None:
            raise DomainConflict("Incomplete intake already has a recovery action")
        if source.partial_job_spec is None:
            raise DomainConflict("Incomplete intake has no structured partial spec")
        now = self._clock()
        job = JobRecord(
            job_spec=source.partial_job_spec,
            state=JobState.INTAKE_COMPLETE,
            created_at=now,
            updated_at=now,
        )
        return self._repository.finish_intake_manually(session_id, job, now)

    @staticmethod
    def _validate_snapshot(
        snapshot: ConversationRepairSnapshot,
        session: IntakeSession,
    ) -> None:
        if (
            snapshot.conversation_id != session.conversation_id
            or snapshot.agent_id != session.expected_agent_id
        ):
            raise DomainConflict("Provider intake recovery correlation mismatch")

    @staticmethod
    def _validate_event(
        event: VerifiedPostCallTranscription,
        session: IntakeSession,
    ) -> None:
        variables = event.dynamic_variables
        if (
            event.conversation_id != session.conversation_id
            or event.agent_id != session.expected_agent_id
            or variables.intake_session_id != session.intake_session_id
            or variables.job_id != session.job_id
            or variables.agent_config_version != session.agent_config_version
        ):
            raise DomainConflict("Provider intake recovery event mismatch")


__all__ = ["IntakeRecoveryService"]
