"""Recovery, structured resume, and manual-finish orchestration tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from services.api.app.contracts import (
    CallStatus,
    DataClassification,
    IntakeSource,
    JobSpecV1,
    JobState,
)
from services.api.app.core.errors import DomainConflict
from services.api.app.integrations.elevenlabs.conversations import (
    ConversationRepairSnapshot,
)
from services.api.app.integrations.elevenlabs.models import (
    ElevenLabsDynamicVariables,
    VerifiedPostCallTranscription,
)
from services.api.app.orchestration.intake_recovery import IntakeRecoveryService
from services.api.app.orchestration.intake_sessions import (
    IntakeDataMode,
    IntakeRecoveryAction,
    IntakeSession,
    IntakeSessionService,
    IntakeSessionStatus,
)
from services.api.app.repositories.memory import InMemoryRepository

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
AGENT_ID = "synthetic-intake-agent"
CONFIG_VERSION = "2026-07-21.2"


def _partial(job_spec: JobSpecV1, job_id) -> JobSpecV1:
    return job_spec.model_copy(
        update={
            "job_id": job_id,
            "intake_source": IntakeSource.VOICE,
            "move_date": None,
            "confirmed": False,
            "confirmed_at": None,
            "locked_version": None,
            "data_classification": DataClassification.REAL_REDACTED,
        },
        deep=True,
    )


def _incomplete(repository, job_spec) -> IntakeSession:
    job_id = uuid4()
    partial = _partial(job_spec, job_id)
    session = IntakeSession(
        job_id=job_id,
        expected_agent_id=AGENT_ID,
        agent_config_version=CONFIG_VERSION,
        data_mode=IntakeDataMode.REAL_REDACTED,
        status=IntakeSessionStatus.INCOMPLETE,
        conversation_id=f"conv_synthetic_{uuid4().hex}",
        partial_job_spec=partial,
        missing_fields=partial.missing_required_fields(),
        terminal_reason="user_ended_before_summary",
        created_at=NOW - timedelta(minutes=2),
        updated_at=NOW - timedelta(minutes=1),
    )
    return repository.create_intake_session(session)


class StubConversationClient:
    def __init__(self, snapshot: ConversationRepairSnapshot) -> None:
        self.snapshot = snapshot

    def fetch_for_repair(self, conversation_id: str) -> ConversationRepairSnapshot:
        assert conversation_id == self.snapshot.conversation_id
        return self.snapshot


class StubMaterializer:
    def __init__(self, repository, partial: JobSpecV1) -> None:
        self.repository = repository
        self.partial = partial
        self.calls = 0

    def materialize(self, event: VerifiedPostCallTranscription):
        self.calls += 1
        session = self.repository.get_intake_session(
            event.dynamic_variables.intake_session_id
        )
        assert session is not None
        updated = session.model_copy(
            update={
                "status": IntakeSessionStatus.INCOMPLETE,
                "partial_job_spec": self.partial,
                "missing_fields": tuple(self.partial.missing_required_fields()),
                "terminal_reason": "user_ended_before_summary",
                "updated_at": event.event_timestamp,
            },
            deep=True,
        )
        self.repository.save_intake_session(updated)


def _session_service(repository) -> IntakeSessionService:
    return IntakeSessionService(
        repository=repository,
        expected_agent_id=AGENT_ID,
        agent_config_version=CONFIG_VERSION,
        clock=lambda: NOW,
    )


def test_recover_routes_done_snapshot_through_canonical_materializer(job_spec):
    repository = InMemoryRepository()
    job_id = uuid4()
    session = IntakeSession(
        job_id=job_id,
        expected_agent_id=AGENT_ID,
        agent_config_version=CONFIG_VERSION,
        data_mode=IntakeDataMode.REAL_REDACTED,
        status=IntakeSessionStatus.IN_PROGRESS,
        conversation_id="conv_synthetic_recover",
        created_at=NOW - timedelta(minutes=1),
        updated_at=NOW - timedelta(minutes=1),
    )
    repository.create_intake_session(session)
    partial = _partial(job_spec, job_id)
    event = VerifiedPostCallTranscription(
        idempotency_key="synthetic-recovery-event",
        event_timestamp=NOW,
        agent_id=AGENT_ID,
        conversation_id=session.conversation_id,
        provider_status="done",
        call_status=CallStatus.COMPLETED,
        dynamic_variables=ElevenLabsDynamicVariables(
            job_id=job_id,
            intake_session_id=session.intake_session_id,
            agent_config_version=CONFIG_VERSION,
        ),
        collected_data={"recording_consent": True},
    )
    materializer = StubMaterializer(repository, partial)
    recovery = IntakeRecoveryService(
        sessions=_session_service(repository),
        repository=repository,
        conversations=StubConversationClient(
            ConversationRepairSnapshot(
                conversation_id=session.conversation_id,
                agent_id=AGENT_ID,
                status="done",
                completed_event=event,
            )
        ),
        materializer=materializer,
        clock=lambda: NOW,
    )

    view = recovery.recover(session.intake_session_id)

    assert view.status is IntakeSessionStatus.INCOMPLETE
    assert view.partial_job_spec == partial
    assert materializer.calls == 1


def test_resume_is_idempotent_and_inherits_mode_and_partial(job_spec):
    repository = InMemoryRepository()
    source = _incomplete(repository, job_spec)
    recovery = IntakeRecoveryService(
        sessions=_session_service(repository),
        repository=repository,
        conversations=None,
        materializer=None,
        clock=lambda: NOW,
    )

    first = recovery.resume(source.intake_session_id)
    second = recovery.resume(source.intake_session_id)

    assert first.intake_session_id == second.intake_session_id
    assert first.data_mode is IntakeDataMode.REAL_REDACTED
    assert first.resumed_from_session_id == source.intake_session_id
    assert first.partial_job_spec is not None
    assert first.partial_job_spec.job_id == first.job_id
    claimed = repository.get_intake_session(source.intake_session_id)
    assert claimed is not None
    assert claimed.recovery_action is IntakeRecoveryAction.RESUME


def test_finish_manually_creates_one_editable_job_and_excludes_resume(job_spec):
    repository = InMemoryRepository()
    source = _incomplete(repository, job_spec)
    recovery = IntakeRecoveryService(
        sessions=_session_service(repository),
        repository=repository,
        conversations=None,
        materializer=None,
        clock=lambda: NOW,
    )

    first = recovery.finish_manually(source.intake_session_id)
    second = recovery.finish_manually(source.intake_session_id)

    assert first == second
    assert first.state is JobState.INTAKE_COMPLETE
    assert first.job_spec == source.partial_job_spec
    assert first.job_spec.confirmed is False
    with pytest.raises(DomainConflict, match="recovery action"):
        recovery.resume(source.intake_session_id)


def test_recover_is_bounded_when_provider_is_not_done(job_spec):
    repository = InMemoryRepository()
    source = _incomplete(repository, job_spec).model_copy(
        update={
            "status": IntakeSessionStatus.IN_PROGRESS,
            "partial_job_spec": None,
            "missing_fields": (),
            "terminal_reason": None,
        },
        deep=True,
    )
    repository.reset()
    repository.create_intake_session(source)
    recovery = IntakeRecoveryService(
        sessions=_session_service(repository),
        repository=repository,
        conversations=StubConversationClient(
            ConversationRepairSnapshot(
                conversation_id=source.conversation_id,
                agent_id=AGENT_ID,
                status="processing",
            )
        ),
        materializer=None,
        clock=lambda: NOW,
    )

    with pytest.raises(DomainConflict, match="not ready"):
        recovery.recover(source.intake_session_id)

    assert repository.get_intake_session(source.intake_session_id) == source
