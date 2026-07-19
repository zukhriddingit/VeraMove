"""Focused browser voice intake-session reservation tests."""

from datetime import UTC, datetime, timedelta

import pytest

from services.api.app.core.errors import DomainConflict
from services.api.app.orchestration.intake_sessions import IntakeSessionService
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
