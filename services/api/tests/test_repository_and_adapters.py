"""Repository and mock adapter boundary tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest

from services.api.app.contracts import (
    CallRecord,
    CallStatus,
    DataClassification,
    IntakeSource,
    JobRecord,
    JobState,
    JobVendorResearchV1,
    VendorSearchQuery,
    VerificationStatus,
)
from services.api.app.core.errors import DomainConflict
from services.api.app.integrations.elevenlabs.mock import MockVoiceProvider
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.orchestration.intake_sessions import (
    IntakeSession,
    IntakeSessionStatus,
)
from services.api.app.orchestration.mock_intelligence import MockIntelligenceProvider
from services.api.app.orchestration.models import (
    CallAttempt,
    CallKind,
    JobEvent,
    VoiceCallReference,
)
from services.api.app.orchestration.providers import IntelligenceProvider, VoiceProvider
from services.api.app.repositories.base import (
    VoiceIntakeCompletion,
    VoiceIntakeFailure,
    VoiceWebhookLease,
    VoiceWebhookMaterialization,
)
from services.api.app.repositories.memory import InMemoryRepository


def make_confirmed_record(job_spec) -> JobRecord:
    confirmed_at = datetime.now(UTC)
    confirmed_spec = job_spec.model_copy(
        update={
            "confirmed": True,
            "confirmed_at": confirmed_at,
            "locked_version": job_spec.version,
        },
        deep=True,
    )
    return JobRecord(
        job_spec=confirmed_spec,
        state=JobState.CONFIRMED,
        created_at=confirmed_at,
        updated_at=confirmed_at,
    )


def test_repository_returns_defensive_copy(job_spec):
    repository = InMemoryRepository()
    now = datetime.now(UTC)
    record = JobRecord(
        job_spec=job_spec,
        state=JobState.INTAKE_COMPLETE,
        created_at=now,
        updated_at=now,
    )
    repository.create(record)
    first = repository.get(job_spec.job_id)
    assert first is not None
    first.state = JobState.FAILED
    stored = repository.get(job_spec.job_id)
    assert stored is not None
    assert stored.state is JobState.INTAKE_COMPLETE


def test_memory_vendor_research_round_trip_is_independent_and_deep_copied(
    fixtures,
    job_spec,
):
    repository = InMemoryRepository()
    record = make_confirmed_record(job_spec)
    repository.create(record)
    candidates = [
        vendor.model_copy(
            update={"data_classification": DataClassification.REAL_REDACTED},
            deep=True,
        )
        for vendor in fixtures.load_vendors()
    ]
    research = JobVendorResearchV1(
        job_id=job_spec.job_id,
        job_spec_version=job_spec.version,
        query=VendorSearchQuery(city="Newton", state="MA"),
        candidates=candidates,
        source="tavily",
        created_at=record.updated_at,
        updated_at=record.updated_at,
    )

    saved = repository.save_vendor_research(research)
    saved.candidates.clear()
    loaded = repository.get_vendor_research(job_spec.job_id, job_spec.version)

    assert loaded is not None
    assert len(loaded.candidates) == 3
    assert repository.get(job_spec.job_id) == record
    repository.reset()
    assert repository.get_vendor_research(job_spec.job_id, job_spec.version) is None


def test_repository_preserves_confirmed_snapshot_and_provider_reference(fixtures, job_spec):
    repository = InMemoryRepository()
    record = make_confirmed_record(job_spec)
    repository.create(record)
    vendor = fixtures.load_vendors()[0]
    attempt = CallAttempt(
        call_id=uuid4(),
        job_id=job_spec.job_id,
        kind=CallKind.QUOTE,
        vendor=vendor,
        job_spec_snapshot=record.job_spec,
        status=CallStatus.PENDING,
        started_at=datetime.now(UTC),
        reference=VoiceCallReference(
            conversation_id="synthetic-conversation-1",
            provider_call_id="synthetic-provider-call-1",
        ),
    )
    repository.create_attempt(attempt)

    stored = repository.get_attempt(attempt.call_id)
    found = repository.find_attempt_by_conversation_id("synthetic-conversation-1")
    assert stored is not None
    assert stored.job_spec_snapshot == record.job_spec
    assert stored.reference == attempt.reference
    assert stored is not attempt
    assert found == stored
    assert repository.list_attempts(job_spec.job_id) == [stored]

    attempt.status = CallStatus.FAILED
    unchanged = repository.get_attempt(attempt.call_id)
    assert unchanged is not None
    assert unchanged.status is CallStatus.PENDING
    repository.save_attempt(attempt)
    assert repository.list_attempts(job_spec.job_id)[0].status is CallStatus.FAILED


def test_repository_aggregates_calls_and_quotes(fixtures, job_spec):
    repository = InMemoryRepository()
    record = make_confirmed_record(job_spec)
    repository.create(record)
    vendor = fixtures.load_vendors()[0]
    call_id = uuid4()
    result = MockVoiceProvider(fixtures).initiate_quote_call(
        record.job_spec,
        vendor,
        call_id,
    )
    assert result.outcome is not None
    assert result.completed_at is not None
    assert result.recording_url is not None
    call = CallRecord(
        call_id=call_id,
        job_id=job_spec.job_id,
        vendor=vendor,
        status=CallStatus.COMPLETED,
        started_at=datetime(2026, 7, 18, 16, 0, tzinfo=UTC),
        completed_at=result.completed_at,
        outcome=result.outcome,
        recording_url=result.recording_url,
    )
    quote = result.outcome.quote
    assert quote is not None

    repository.save_call(call)
    repository.save_quote(quote)

    assert repository.list_calls(job_spec.job_id) == [call]
    assert repository.list_quotes(job_spec.job_id) == [quote]
    stored = repository.get(job_spec.job_id)
    assert stored is not None
    assert stored.calls == [call]
    assert stored.quotes == [quote]

    stored.calls[0].status = CallStatus.FAILED
    stored.quotes[0].concessions.append("mutated outside repository")
    assert repository.list_calls(job_spec.job_id)[0].status is CallStatus.COMPLETED
    assert "mutated outside repository" not in repository.list_quotes(
        job_spec.job_id,
    )[0].concessions


def test_webhook_reservation_and_events_are_process_local(job_spec):
    repository = InMemoryRepository()
    repository.create(make_confirmed_record(job_spec))
    event = JobEvent(
        job_id=job_spec.job_id,
        event_type="call.completed",
        occurred_at=datetime.now(UTC),
        metadata={"provider": "synthetic"},
    )

    assert repository.reserve_webhook("synthetic-event-1") is True
    assert repository.reserve_webhook("synthetic-event-1") is False
    repository.append_event(event)
    listed = repository.list_events(job_spec.job_id)
    assert listed == [event]
    assert listed[0] is not event
    listed[0].metadata["provider"] = "mutated"
    assert repository.list_events(job_spec.job_id)[0].metadata["provider"] == "synthetic"


def _completed_materialization(
    repository,
    record,
    attempt,
    fixtures,
    *,
    event_type="post_call_transcription",
):
    result = MockVoiceProvider(fixtures).initiate_quote_call(
        record.job_spec,
        attempt.vendor,
        attempt.call_id,
    )
    assert result.outcome is not None
    assert result.outcome.quote is not None
    assert result.completed_at is not None
    assert result.recording_url is not None
    completed_attempt = attempt.model_copy(
        update={
            "status": CallStatus.COMPLETED,
            "completed_at": result.completed_at,
            "provider_version_id": "synthetic-provider-version",
        },
        deep=True,
    )
    call = CallRecord(
        call_id=attempt.call_id,
        job_id=attempt.job_id,
        vendor=attempt.vendor,
        status=CallStatus.COMPLETED,
        started_at=attempt.started_at,
        completed_at=result.completed_at,
        outcome=result.outcome,
        recording_url=result.recording_url,
    )
    current = repository.get(attempt.job_id)
    assert current is not None
    quote = result.outcome.quote
    current.calls = [item for item in current.calls if item.call_id != call.call_id]
    current.calls.append(call)
    current.quotes = [item for item in current.quotes if item.quote_id != quote.quote_id]
    current.quotes.append(quote)
    current.state = JobState.CALLING
    current.updated_at = result.completed_at
    event = JobEvent(
        job_id=attempt.job_id,
        call_id=attempt.call_id,
        event_type=event_type,
        occurred_at=result.completed_at,
        metadata={"provider_status": "done"},
    )
    return VoiceWebhookMaterialization(
        attempt=completed_attempt,
        call=call,
        quote=quote,
        job=current,
        event=event,
        expected_revision=repository.get_job_revision(attempt.job_id),
    )


def _intake_session(job_spec, *, now, conversation_id="synthetic-intake-conversation"):
    return IntakeSession(
        intake_session_id=uuid4(),
        job_id=job_spec.job_id,
        expected_agent_id="synthetic-intake-agent",
        agent_config_version="synthetic-config-v1",
        status=IntakeSessionStatus.IN_PROGRESS,
        conversation_id=conversation_id,
        created_at=now - timedelta(minutes=1),
        updated_at=now - timedelta(minutes=1),
    )


def _intake_completion(session, job_spec, *, now, event_type="post_call_transcription"):
    voice_spec = job_spec.model_copy(
        update={
            "intake_source": IntakeSource.VOICE,
            "confirmed": False,
            "confirmed_at": None,
            "locked_version": None,
        },
        deep=True,
    )
    job = JobRecord(
        job_spec=voice_spec,
        state=JobState.INTAKE_COMPLETE,
        created_at=now,
        updated_at=now,
    )
    completed_session = session.model_copy(
        update={
            "status": IntakeSessionStatus.COMPLETED,
            "updated_at": now,
            "completed_at": now,
        },
        deep=True,
    )
    event = JobEvent(
        job_id=session.job_id,
        event_type=event_type,
        occurred_at=now,
        metadata={"provider_status": "done"},
    )
    return VoiceIntakeCompletion(
        session=completed_session,
        job=job,
        event=event,
    )


def _intake_failure(session, *, now, event_type="call_initiation_failure"):
    return VoiceIntakeFailure(
        session=session.model_copy(
            update={
                "status": IntakeSessionStatus.FAILED,
                "failure_code": "provider_no_answer",
                "updated_at": now,
            },
            deep=True,
        ),
        event_type=event_type,
    )


def test_voice_intake_materialization_models_reject_identity_mismatch(job_spec):
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    session = _intake_session(job_spec, now=now)
    completion = _intake_completion(session, job_spec, now=now)

    with pytest.raises(ValueError, match="identity"):
        VoiceIntakeCompletion(
            session=completion.session,
            job=completion.job,
            event=completion.event.model_copy(update={"job_id": uuid4()}, deep=True),
        )
    with pytest.raises(ValueError, match="failed"):
        VoiceIntakeFailure(
            session=session,
            event_type="call_initiation_failure",
        )
    with pytest.raises(ValueError, match="forbidden"):
        VoiceIntakeCompletion(
            session=completion.session,
            job=completion.job,
            event=completion.event.model_copy(
                update={"metadata": {"analysis": "private provider output"}},
                deep=True,
            ),
        )


def test_voice_intake_completion_is_atomic_and_duplicate_safe(job_spec):
    repository = InMemoryRepository()
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    session = _intake_session(job_spec, now=now)
    repository.create_intake_session(session)
    materialization = _intake_completion(session, job_spec, now=now)
    token = uuid4()
    lease = VoiceWebhookLease(
        idempotency_key="synthetic-intake-completion-event",
        event_type=materialization.event.event_type,
        lease_token=token,
        lease_expires_at=now + timedelta(minutes=5),
        now=now,
    )
    assert repository.claim_voice_webhook_receipt(lease).claimed

    result = repository.finalize_voice_intake_webhook(
        lease.idempotency_key,
        token,
        materialization,
        now,
    )

    assert result.model_dump() == {"processed": True, "duplicate": False}
    assert repository.get(session.job_id) == materialization.job
    assert repository.get_intake_session(session.intake_session_id) == materialization.session
    assert repository.list_events(session.job_id) == [materialization.event]
    duplicate = repository.finalize_voice_intake_webhook(
        lease.idempotency_key,
        uuid4(),
        materialization,
        now,
    )
    assert duplicate.model_dump() == {"processed": True, "duplicate": True}


def test_voice_intake_failure_rejects_wrong_token_without_partial_write(job_spec):
    repository = InMemoryRepository()
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    session = _intake_session(job_spec, now=now)
    repository.create_intake_session(session)
    materialization = _intake_failure(session, now=now)
    token = uuid4()
    lease = VoiceWebhookLease(
        idempotency_key="synthetic-intake-failure-event",
        event_type=materialization.event_type,
        lease_token=token,
        lease_expires_at=now + timedelta(minutes=5),
        now=now,
    )
    assert repository.claim_voice_webhook_receipt(lease).claimed

    with pytest.raises(DomainConflict, match="lease"):
        repository.finalize_voice_intake_webhook(
            lease.idempotency_key,
            uuid4(),
            materialization,
            now,
        )
    assert repository.get_intake_session(session.intake_session_id) == session
    assert repository.get(session.job_id) is None

    result = repository.finalize_voice_intake_webhook(
        lease.idempotency_key,
        token,
        materialization,
        now,
    )
    assert result.duplicate is False
    assert repository.get_intake_session(session.intake_session_id) == materialization.session
    assert repository.get(session.job_id) is None


def test_voice_intake_completion_rejects_divergent_existing_job_atomically(job_spec):
    repository = InMemoryRepository()
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    session = _intake_session(job_spec, now=now)
    repository.create_intake_session(session)
    materialization = _intake_completion(session, job_spec, now=now)
    divergent = materialization.job.model_copy(update={"state": JobState.FAILED}, deep=True)
    repository.create(divergent)
    token = uuid4()
    lease = VoiceWebhookLease(
        idempotency_key="synthetic-intake-divergent-event",
        event_type=materialization.event.event_type,
        lease_token=token,
        lease_expires_at=now + timedelta(minutes=5),
        now=now,
    )
    repository.claim_voice_webhook_receipt(lease)

    with pytest.raises(DomainConflict, match="different canonical job"):
        repository.finalize_voice_intake_webhook(
            lease.idempotency_key,
            token,
            materialization,
            now,
        )

    assert repository.get(session.job_id) == divergent
    assert repository.get_intake_session(session.intake_session_id) == session
    assert repository.list_events(session.job_id) == []


def test_voice_webhook_receipt_has_one_unexpired_thread_winner():
    repository = InMemoryRepository()
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    tokens = [uuid4() for _ in range(8)]
    barrier = Barrier(len(tokens))

    def claim(token):
        barrier.wait()
        return repository.claim_voice_webhook_receipt(
            VoiceWebhookLease(
                idempotency_key="synthetic-concurrent-event",
                event_type="post_call_transcription",
                lease_token=token,
                lease_expires_at=now + timedelta(minutes=5),
                now=now,
            )
        )

    with ThreadPoolExecutor(max_workers=len(tokens)) as pool:
        results = list(pool.map(claim, tokens))

    assert sum(result.claimed for result in results) == 1
    assert not any(result.processed for result in results)


def test_voice_webhook_receipt_reclaims_retryable_failure_and_expired_lease():
    repository = InMemoryRepository()
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    first_token = uuid4()
    second_token = uuid4()
    first = VoiceWebhookLease(
        idempotency_key="synthetic-retryable-event",
        event_type="post_call_transcription",
        lease_token=first_token,
        lease_expires_at=now + timedelta(minutes=1),
        now=now,
    )
    assert repository.claim_voice_webhook_receipt(first).claimed is True
    failed = repository.fail_voice_webhook_receipt(
        first.idempotency_key,
        first_token,
        "transient_storage",
        True,
        now,
    )
    assert failed.retryable is True
    reclaimed = repository.claim_voice_webhook_receipt(
        first.model_copy(update={"lease_token": second_token}, deep=True)
    )
    assert reclaimed.claimed is True

    expiring_token = uuid4()
    expiring = VoiceWebhookLease(
        idempotency_key="synthetic-expired-event",
        event_type="post_call_transcription",
        lease_token=expiring_token,
        lease_expires_at=now + timedelta(seconds=1),
        now=now,
    )
    assert repository.claim_voice_webhook_receipt(expiring).claimed is True
    expired_reclaim = repository.claim_voice_webhook_receipt(
        expiring.model_copy(
            update={
                "lease_token": uuid4(),
                "lease_expires_at": now + timedelta(minutes=6),
                "now": now + timedelta(minutes=5),
            },
            deep=True,
        )
    )
    assert expired_reclaim.claimed is True


def test_voice_webhook_finalize_rejects_wrong_token_and_acks_processed_duplicate(
    fixtures,
    job_spec,
):
    repository = InMemoryRepository()
    record = make_confirmed_record(job_spec)
    repository.create(record)
    attempt = CallAttempt(
        call_id=uuid4(),
        job_id=job_spec.job_id,
        kind=CallKind.QUOTE,
        vendor=fixtures.load_vendors()[0],
        job_spec_snapshot=record.job_spec,
        status=CallStatus.PENDING,
        started_at=datetime(2026, 7, 19, 12, 0, tzinfo=UTC),
        reference=VoiceCallReference(
            conversation_id="synthetic-finalize-conversation",
            provider_call_id="synthetic-finalize-provider-call",
        ),
    )
    repository.create_attempt(attempt)
    materialization = _completed_materialization(repository, record, attempt, fixtures)
    now = datetime(2026, 7, 19, 12, 5, tzinfo=UTC)
    token = uuid4()
    lease = VoiceWebhookLease(
        idempotency_key="synthetic-finalize-event",
        event_type="post_call_transcription",
        lease_token=token,
        lease_expires_at=now + timedelta(minutes=5),
        now=now,
    )
    assert repository.claim_voice_webhook_receipt(lease).claimed is True

    with pytest.raises(DomainConflict, match="lease"):
        repository.finalize_voice_webhook(
            lease.idempotency_key,
            uuid4(),
            materialization,
            now,
        )

    result = repository.finalize_voice_webhook(
        lease.idempotency_key,
        token,
        materialization,
        now,
    )
    assert result.model_dump() == {"processed": True, "duplicate": False}
    duplicate = repository.finalize_voice_webhook(
        lease.idempotency_key,
        uuid4(),
        materialization,
        now,
    )
    assert duplicate.model_dump() == {"processed": True, "duplicate": True}
    replay = repository.claim_voice_webhook_receipt(
        lease.model_copy(update={"lease_token": uuid4()}, deep=True)
    )
    assert replay.model_dump() == {"claimed": False, "processed": True}
    stored = repository.get(job_spec.job_id)
    assert stored is not None
    assert stored.calls == [materialization.call]
    assert stored.quotes == [materialization.quote]
    assert repository.get_attempt(attempt.call_id) == materialization.attempt
    assert repository.list_events(job_spec.job_id) == [materialization.event]


def test_three_out_of_order_finalizations_retry_revision_without_lost_results(
    fixtures,
    job_spec,
):
    repository = InMemoryRepository()
    record = make_confirmed_record(job_spec)
    repository.create(record)
    attempts = []
    for index, vendor in enumerate(fixtures.load_vendors()):
        attempt = CallAttempt(
            call_id=uuid4(),
            job_id=job_spec.job_id,
            kind=CallKind.QUOTE,
            vendor=vendor,
            job_spec_snapshot=record.job_spec,
            destination_slot=index,
            status=CallStatus.PENDING,
            started_at=datetime(2026, 7, 19, 12, index, tzinfo=UTC),
            reference=VoiceCallReference(
                conversation_id=f"synthetic-out-of-order-conversation-{index}",
                provider_call_id=f"synthetic-out-of-order-provider-{index}",
            ),
        )
        repository.create_attempt(attempt)
        attempts.append(attempt)

    now = datetime(2026, 7, 19, 12, 10, tzinfo=UTC)
    tokens = [uuid4() for _ in attempts]
    keys = [f"synthetic-out-of-order-event-{index}" for index in range(3)]
    for key, token in zip(keys, tokens, strict=True):
        assert repository.claim_voice_webhook_receipt(
            VoiceWebhookLease(
                idempotency_key=key,
                event_type="post_call_transcription",
                lease_token=token,
                lease_expires_at=now + timedelta(minutes=5),
                now=now,
            )
        ).claimed

    first_attempt = Barrier(3)

    def finalize(index):
        materialization = _completed_materialization(
            repository,
            record,
            attempts[index],
            fixtures,
        )
        first_attempt.wait()
        while True:
            try:
                return repository.finalize_voice_webhook(
                    keys[index],
                    tokens[index],
                    materialization,
                    now,
                )
            except DomainConflict as exc:
                assert "revision" in str(exc)
                materialization = _completed_materialization(
                    repository,
                    record,
                    attempts[index],
                    fixtures,
                )

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(finalize, reversed(range(3))))

    assert all(result.processed and not result.duplicate for result in results)
    stored = repository.get(job_spec.job_id)
    assert stored is not None
    assert {call.call_id for call in stored.calls} == {
        attempt.call_id for attempt in attempts
    }
    assert len(stored.quotes) == 3
    assert len(repository.list_events(job_spec.job_id)) == 3
    assert repository.get_job_revision(job_spec.job_id) == 3


def test_verified_competitor_excludes_target_and_unverified_quotes(
    fixtures,
    job_spec,
    monkeypatch,
):
    repository = InMemoryRepository()
    repository.create(make_confirmed_record(job_spec))
    quotes = fixtures.load_initial_quotes()
    for quote in quotes:
        repository.save_quote(quote.model_copy(update={"job_id": job_spec.job_id}))

    selected = repository.get_verified_competing_quote(
        job_spec.job_id,
        target_vendor_id=quotes[2].vendor.vendor_id,
        job_spec_version=job_spec.version,
    )

    assert selected is not None
    assert selected.vendor.slug == "clearpath-movers"

    without_evidence = quotes[0].model_copy(
        update={"job_id": job_spec.job_id, "transcript_evidence": []},
    )
    monkeypatch.setattr(repository, "list_quotes", lambda _job_id: [without_evidence])
    assert (
        repository.get_verified_competing_quote(
            job_spec.job_id,
            target_vendor_id=quotes[2].vendor.vendor_id,
            job_spec_version=job_spec.version,
        )
        is None
    )
    monkeypatch.undo()

    repository.save_quote(
        quotes[0].model_copy(
            update={"job_id": job_spec.job_id, "verified_data": {}},
        ),
    )
    assert (
        repository.get_verified_competing_quote(
            job_spec.job_id,
            target_vendor_id=quotes[2].vendor.vendor_id,
            job_spec_version=job_spec.version,
        )
        is None
    )
    assert (
        repository.get_verified_competing_quote(
            job_spec.job_id,
            target_vendor_id=quotes[2].vendor.vendor_id,
            job_spec_version="unsupported-version",
        )
        is None
    )


def test_repository_rejects_changes_to_locked_job_spec(job_spec):
    repository = InMemoryRepository()
    now = datetime.now(UTC)
    confirmed = job_spec.model_copy(
        update={
            "confirmed": True,
            "confirmed_at": now,
            "locked_version": job_spec.version,
        },
        deep=True,
    )
    record = JobRecord(
        job_spec=confirmed,
        state=JobState.CONFIRMED,
        created_at=now,
        updated_at=now,
    )
    repository.create(record)
    record.job_spec = record.job_spec.model_copy(
        update={"bedroom_count": (record.job_spec.bedroom_count or 0) + 1},
        deep=True,
    )
    with pytest.raises(DomainConflict, match="locked"):
        repository.save(record)


def test_new_mock_provider_boundaries_are_structurally_compatible(fixtures):
    voice: VoiceProvider = MockVoiceProvider(fixtures)
    intelligence: IntelligenceProvider = MockIntelligenceProvider(
        fixtures,
        MockNegotiationGateway(fixtures),
    )

    assert voice.initial_call_limit == 3
    extracted = intelligence.extract_document("Synthetic demo document.")
    assert extracted.intake_source is IntakeSource.DOCUMENT


def test_mock_negotiation_improves_total(fixtures, job_spec):
    quotes = fixtures.load_initial_quotes()
    improved = MockNegotiationGateway(fixtures).negotiate(job_spec, quotes, quotes[0])
    assert improved.negotiated_total < improved.original_total
    assert improved.verification_status is VerificationStatus.VERIFIED
    assert improved.verified_data["competing_quote_id"] == str(quotes[0].quote_id)


def test_mock_vendor_discovery_is_synthetic(fixtures):
    vendors = MockVendorDiscoveryGateway(fixtures).discover("origin", "destination")
    assert [vendor.slug for vendor in vendors] == [
        "clearpath-movers",
        "budgetlift-moving",
        "northstar-relocation",
    ]
