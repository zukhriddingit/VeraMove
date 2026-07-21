"""Focused browser voice intake-session reservation tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from services.api.app.contracts import DataClassification, IntakeSource, JobSpecV1
from services.api.app.core.errors import DomainConflict
from services.api.app.orchestration.intake_sessions import (
    TERMINAL_INTAKE_STATUSES,
    IntakeDataMode,
    IntakeRecoveryAction,
    IntakeSession,
    IntakeSessionService,
    IntakeSessionStatus,
    validate_intake_session_update,
)
from services.api.app.repositories.memory import InMemoryRepository

NOW = datetime(2026, 7, 19, 14, 0, tzinfo=UTC)


def make_service() -> IntakeSessionService:
    return IntakeSessionService(
        repository=InMemoryRepository(),
        expected_agent_id="agent_synthetic_intake",
        agent_config_version="2026-07-19.browser-v1",
        clock=lambda: NOW,
    )


def test_web_session_reserves_one_browser_credential_without_creating_job() -> None:
    service = make_service()
    created = service.create_web_session()

    reserved = service.reserve_browser_credential(created.intake_session_id)

    assert reserved.browser_credential_issued_at == NOW
    assert reserved.status.value == "pending"
    assert reserved.conversation_id is None
    assert service.repository.get(created.job_id) is None

    with pytest.raises(DomainConflict, match="already received"):
        service.reserve_browser_credential(created.intake_session_id)


def test_telephone_and_terminal_sessions_cannot_reserve_browser_credentials() -> None:
    service = make_service()
    telephone = service.create_pre_call_session(
        agent_id="agent_synthetic_intake",
        provider_call_key="CA_synthetic_phone_call",
    )
    with pytest.raises(DomainConflict, match="web intake"):
        service.reserve_browser_credential(telephone.intake_session_id)

    web = service.create_web_session()
    service.fail_session(web.intake_session_id, "synthetic_failure")
    with pytest.raises(DomainConflict, match="pending"):
        service.reserve_browser_credential(web.intake_session_id)


def test_reservation_timestamp_cannot_change() -> None:
    service = make_service()
    created = service.create_web_session()
    reserved = service.reserve_browser_credential(created.intake_session_id)
    changed = reserved.model_copy(
        update={"browser_credential_issued_at": NOW + timedelta(seconds=1)},
        deep=True,
    )

    with pytest.raises(DomainConflict, match="credential reservation"):
        service.repository.save_intake_session(changed)


def _partial_voice_spec(job_spec, job_id):
    payload = job_spec.model_dump(mode="json")
    payload.update(
        {
            "job_id": str(job_id),
            "intake_source": IntakeSource.VOICE,
            "move_date": None,
            "data_classification": DataClassification.ROLE_PLAY,
            "confirmed": False,
            "confirmed_at": None,
            "locked_version": None,
        }
    )
    return JobSpecV1.model_validate(payload)


def test_incomplete_intake_requires_partial_spec_and_exact_missing_fields(job_spec) -> None:
    job_id = uuid4()
    partial = _partial_voice_spec(job_spec, job_id)

    session = IntakeSession(
        job_id=job_id,
        expected_agent_id="agent_synthetic_intake",
        agent_config_version="2026-07-21.2",
        status=IntakeSessionStatus.INCOMPLETE,
        conversation_id="conv_synthetic_partial",
        data_mode=IntakeDataMode.SUPERVISED_ROLE_PLAY,
        partial_job_spec=partial,
        missing_fields=partial.missing_required_fields(),
        terminal_reason="user_ended_before_summary",
        created_at=NOW,
        updated_at=NOW,
    )

    assert session.partial_job_spec == partial
    assert session.missing_fields == tuple(partial.missing_required_fields())
    assert session.status in TERMINAL_INTAKE_STATUSES


def test_incomplete_intake_rejects_raw_transcript_shape(job_spec) -> None:
    job_id = uuid4()
    partial = _partial_voice_spec(job_spec, job_id)

    with pytest.raises(ValidationError, match="transcript"):
        IntakeSession(
            job_id=job_id,
            expected_agent_id="agent_synthetic_intake",
            agent_config_version="2026-07-21.2",
            status=IntakeSessionStatus.INCOMPLETE,
            conversation_id="conv_synthetic_partial",
            partial_job_spec=partial.model_dump(mode="json") | {"transcript": []},
            missing_fields=partial.missing_required_fields(),
            terminal_reason="user_ended_before_summary",
            created_at=NOW,
            updated_at=NOW,
        )


def test_incomplete_intake_rejects_missing_field_drift(job_spec) -> None:
    job_id = uuid4()
    partial = _partial_voice_spec(job_spec, job_id)

    with pytest.raises(ValidationError, match="missing_fields"):
        IntakeSession(
            job_id=job_id,
            expected_agent_id="agent_synthetic_intake",
            agent_config_version="2026-07-21.2",
            status=IntakeSessionStatus.INCOMPLETE,
            conversation_id="conv_synthetic_partial",
            partial_job_spec=partial,
            missing_fields=[],
            terminal_reason="user_ended_before_summary",
            created_at=NOW,
            updated_at=NOW,
        )


def test_intake_mode_and_partial_snapshot_cannot_change_after_creation(job_spec) -> None:
    job_id = uuid4()
    partial = _partial_voice_spec(job_spec, job_id)
    current = IntakeSession(
        job_id=job_id,
        expected_agent_id="agent_synthetic_intake",
        agent_config_version="2026-07-21.2",
        status=IntakeSessionStatus.INCOMPLETE,
        conversation_id="conv_synthetic_partial",
        partial_job_spec=partial,
        missing_fields=partial.missing_required_fields(),
        terminal_reason="user_ended_before_summary",
        created_at=NOW,
        updated_at=NOW,
    )
    changed = current.model_copy(
        update={"data_mode": IntakeDataMode.REAL_REDACTED},
        deep=True,
    )

    with pytest.raises(DomainConflict, match="intake mode"):
        validate_intake_session_update(current, changed)


def test_incomplete_recovery_action_requires_target(job_spec) -> None:
    job_id = uuid4()
    partial = _partial_voice_spec(job_spec, job_id)

    with pytest.raises(ValidationError, match="recovery_target_id"):
        IntakeSession(
            job_id=job_id,
            expected_agent_id="agent_synthetic_intake",
            agent_config_version="2026-07-21.2",
            status=IntakeSessionStatus.INCOMPLETE,
            conversation_id="conv_synthetic_partial",
            partial_job_spec=partial,
            missing_fields=partial.missing_required_fields(),
            terminal_reason="user_ended_before_summary",
            recovery_action=IntakeRecoveryAction.RESUME,
            created_at=NOW,
            updated_at=NOW,
        )


def test_web_session_records_explicit_data_mode() -> None:
    service = make_service()

    created = service.create_web_session(data_mode=IntakeDataMode.REAL_REDACTED)

    assert created.data_mode is IntakeDataMode.REAL_REDACTED
