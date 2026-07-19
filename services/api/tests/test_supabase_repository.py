"""Repository-contract tests for persistent Supabase storage."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from services.api.app.contracts import (
    CallRecord,
    CallStatus,
    DataClassification,
    JobRecord,
    JobState,
    ProvenanceReference,
    ProvenanceType,
    VerificationStatus,
)
from services.api.app.core.errors import (
    DomainConflict,
    DuplicateResource,
    ProviderRequestError,
)
from services.api.app.integrations.elevenlabs.mock import MockVoiceProvider
from services.api.app.orchestration.intake_sessions import (
    IntakeSession,
    IntakeSessionStatus,
)
from services.api.app.orchestration.models import (
    CallAttempt,
    CallKind,
    JobEvent,
    VoiceCallReference,
)
from services.api.app.repositories.supabase import SupabaseRepository
from services.api.app.repositories.supabase_client import SupabaseDuplicate

FIXED_NOW = datetime(2026, 7, 19, 1, 30, tzinfo=UTC)


class FakeSupabaseTableClient:
    """Small PostgREST-semantic fake; no network or Supabase project is used."""

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict[str, Any]]] = {
            name: {}
            for name in (
                "jobs",
                "vendors",
                "call_attempts",
                "calls",
                "quotes",
                "transcript_evidence",
                "recommendations",
                "event_log",
                "intake_sessions",
            )
        }
        self.operations: list[tuple[str, str, dict[str, Any]]] = []
        self.failure: Exception | None = None

    def select_many(
        self,
        table: str,
        filters: dict[str, str],
    ) -> list[dict[str, Any]]:
        self._maybe_fail()
        self.operations.append(("select", table, deepcopy(filters)))
        rows = list(self.tables[table].values())
        for column, expression in filters.items():
            operator, expected = expression.split(".", 1)
            assert operator == "eq"
            rows = [row for row in rows if str(row.get(column)) == expected]
        return deepcopy(rows)

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        self._maybe_fail()
        self.operations.append(("insert", table, deepcopy(row)))
        key = str(row["id"])
        if key in self.tables[table] or self._has_duplicate_unique_value(table, row):
            raise SupabaseDuplicate("duplicate")
        self.tables[table][key] = deepcopy(row)
        return deepcopy(row)

    def upsert(
        self,
        table: str,
        row: dict[str, Any],
        on_conflict: str,
    ) -> dict[str, Any]:
        self._maybe_fail()
        assert on_conflict == "id"
        self.operations.append(("upsert", table, deepcopy(row)))
        key = str(row[on_conflict])
        self.tables[table][key] = {
            **self.tables[table].get(key, {}),
            **deepcopy(row),
        }
        return deepcopy(self.tables[table][key])

    def update(
        self,
        table: str,
        filters: dict[str, str],
        values: dict[str, Any],
    ) -> dict[str, Any]:
        self._maybe_fail()
        matches = self.select_many(table, filters)
        assert len(matches) == 1
        key = str(matches[0]["id"])
        self.tables[table][key].update(deepcopy(values))
        self.operations.append(("update", table, deepcopy(values)))
        return deepcopy(self.tables[table][key])

    def _has_duplicate_unique_value(self, table: str, row: dict[str, Any]) -> bool:
        unique_columns = {
            "event_log": ("idempotency_key",),
            "call_attempts": (
                "conversation_id",
                "external_call_id",
                "idempotency_key",
            ),
            "calls": ("external_call_id", "idempotency_key"),
            "intake_sessions": (
                "reserved_job_id",
                "provider_call_key_hash",
                "conversation_id",
            ),
            "vendors": ("slug",),
        }.get(table, ())
        return any(
            row.get(column) is not None
            and any(existing.get(column) == row[column] for existing in self.tables[table].values())
            for column in unique_columns
        )

    def _maybe_fail(self) -> None:
        if self.failure is not None:
            raise self.failure


@pytest.fixture
def table_client() -> FakeSupabaseTableClient:
    return FakeSupabaseTableClient()


@pytest.fixture
def repository(table_client) -> SupabaseRepository:
    return SupabaseRepository(table_client)


@pytest.fixture
def confirmed_record(job_spec) -> JobRecord:
    confirmed = job_spec.model_copy(
        update={
            "confirmed": True,
            "confirmed_at": FIXED_NOW,
            "locked_version": job_spec.version,
        },
        deep=True,
    )
    return JobRecord(
        job_spec=confirmed,
        state=JobState.CONFIRMED,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )


def make_attempt(confirmed_record, vendor) -> CallAttempt:
    return CallAttempt(
        call_id=uuid4(),
        job_id=confirmed_record.job_spec.job_id,
        kind=CallKind.QUOTE,
        vendor=vendor,
        job_spec_snapshot=confirmed_record.job_spec,
        status=CallStatus.PENDING,
        started_at=FIXED_NOW,
        reference=VoiceCallReference(
            conversation_id="synthetic-conversation",
            provider_call_id="synthetic-provider-call",
        ),
    )


def test_supabase_job_round_trip_and_confirmed_lock(
    repository,
    job_spec,
):
    initial = JobRecord(
        job_spec=job_spec,
        state=JobState.INTAKE_COMPLETE,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    created = repository.create(initial)
    assert repository.get(job_spec.job_id) == created
    assert created is not initial

    confirmed = created.model_copy(
        update={
            "job_spec": created.job_spec.model_copy(
                update={
                    "confirmed": True,
                    "confirmed_at": FIXED_NOW,
                    "locked_version": "1.0",
                }
            ),
            "state": JobState.CONFIRMED,
        },
        deep=True,
    )
    repository.save(confirmed)
    mutated = confirmed.model_copy(
        update={
            "job_spec": confirmed.job_spec.model_copy(update={"insurance_preference": "Changed"})
        },
        deep=True,
    )
    with pytest.raises(DomainConflict, match="locked"):
        repository.save(mutated)


def test_supabase_create_maps_duplicate_job(repository, confirmed_record):
    repository.create(confirmed_record)
    with pytest.raises(DuplicateResource, match="already exists"):
        repository.create(confirmed_record)


def test_supabase_attempt_round_trip_and_provider_lookup(
    repository,
    table_client,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    attempt = make_attempt(confirmed_record, fixtures.load_vendors()[0])

    created = repository.create_attempt(attempt)
    assert created == attempt
    assert created is not attempt
    assert repository.get_attempt(attempt.call_id) == attempt
    assert repository.list_attempts(attempt.job_id) == [attempt]
    assert repository.find_attempt_by_conversation_id("synthetic-conversation") == attempt
    row = table_client.tables["call_attempts"][str(attempt.call_id)]
    assert row["conversation_id"] == "synthetic-conversation"
    assert row["external_call_id"] == "synthetic-provider-call"
    assert table_client.operations[-1] == (
        "select",
        "call_attempts",
        {"conversation_id": "eq.synthetic-conversation"},
    )

    updated = attempt.model_copy(
        update={"status": CallStatus.FAILED, "completed_at": FIXED_NOW},
        deep=True,
    )
    repository.save_attempt(updated)
    assert repository.get_attempt(attempt.call_id) == updated


def test_supabase_canonical_call_and_quote_upsert_exact_aggregate(
    repository,
    table_client,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    vendor = fixtures.load_vendors()[0]
    attempt = make_attempt(confirmed_record, vendor)
    repository.create_attempt(attempt)
    result = MockVoiceProvider(fixtures).initiate_quote_call(
        confirmed_record.job_spec,
        vendor,
        attempt.call_id,
    )
    assert result.outcome is not None
    assert result.recording_url is not None
    call = CallRecord(
        call_id=attempt.call_id,
        job_id=attempt.job_id,
        vendor=vendor,
        status=CallStatus.COMPLETED,
        started_at=FIXED_NOW,
        completed_at=result.completed_at,
        outcome=result.outcome,
        recording_url=result.recording_url,
    )
    quote = result.outcome.quote
    assert quote is not None

    assert repository.save_call(call) == call
    assert repository.save_call(call) == call
    assert repository.get_attempt(attempt.call_id) == attempt
    assert repository.list_attempts(attempt.job_id) == [attempt]
    assert repository.find_attempt_by_conversation_id("synthetic-conversation") == attempt
    assert repository.save_quote(quote) == quote
    assert repository.list_calls(attempt.job_id) == [call]
    assert repository.list_quotes(attempt.job_id) == [quote]
    stored = repository.get(attempt.job_id)
    assert stored is not None
    assert stored.calls == [call]
    assert stored.quotes == [quote]

    call_row = table_client.tables["calls"][str(attempt.call_id)]
    assert call_row["record_type"] == "canonical"
    assert call_row["external_call_id"] == "synthetic-provider-call"
    assert str(attempt.call_id) in table_client.tables["call_attempts"]
    quote_row = table_client.tables["quotes"][str(quote.quote_id)]
    assert quote_row["manually_fabricated"] is False
    assert quote_row["verified_payload"] == quote.verified_data
    assert len(table_client.tables["transcript_evidence"]) == len(quote.transcript_evidence)


def test_supabase_round_trips_discovered_vendor_role_play_outcome(
    repository,
    table_client,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    vendor = fixtures.load_vendors()[0].model_copy(
        update={
            "vendor_id": uuid4(),
            "name": "Example Moving Cooperative",
            "slug": "example-moving-cooperative",
            "behavior_summary": ("Role-play discovery candidate; no real behavior is inferred."),
            "contact_label": "Role-play channel; no contact details stored.",
            "data_classification": DataClassification.ROLE_PLAY,
            "provenance": [
                ProvenanceReference(
                    source_type=ProvenanceType.TAVILY,
                    source_id="vendor.example.com",
                    location="https://vendor.example.com/moving",
                )
            ],
        },
        deep=True,
    )
    attempt = make_attempt(confirmed_record, vendor)
    repository.create_attempt(attempt)
    result = MockVoiceProvider(fixtures).initiate_quote_call(
        confirmed_record.job_spec,
        vendor,
        attempt.call_id,
    )
    assert result.outcome is not None
    assert result.outcome.quote is not None
    assert result.completed_at is not None
    assert result.recording_url is not None
    quote = result.outcome.quote
    call = CallRecord(
        call_id=attempt.call_id,
        job_id=attempt.job_id,
        vendor=vendor,
        status=CallStatus.COMPLETED,
        started_at=FIXED_NOW,
        completed_at=result.completed_at,
        outcome=result.outcome,
        recording_url=result.recording_url,
    )

    repository.save_call(call)
    repository.save_quote(quote)

    stored = repository.get(attempt.job_id)
    assert stored is not None
    assert stored.calls == [call]
    assert stored.quotes == [quote]
    assert (
        table_client.tables["vendors"][str(vendor.vendor_id)]["data_classification"]
        == DataClassification.ROLE_PLAY.value
    )
    assert (
        table_client.tables["quotes"][str(quote.quote_id)]["data_classification"]
        == DataClassification.ROLE_PLAY.value
    )
    assert all(
        row["data_classification"] == DataClassification.ROLE_PLAY.value
        for row in table_client.tables["transcript_evidence"].values()
    )


def test_supabase_save_persists_recommendation(
    repository,
    table_client,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    recommendation = fixtures.load_recommendation().model_copy(
        update={"job_id": confirmed_record.job_spec.job_id},
        deep=True,
    )
    completed = confirmed_record.model_copy(
        update={
            "state": JobState.COMPLETED,
            "recommendation": recommendation,
            "updated_at": FIXED_NOW,
        },
        deep=True,
    )

    repository.save(completed)

    row = table_client.tables["recommendations"][str(recommendation.recommendation_id)]
    assert row["payload"] == recommendation.model_dump(mode="json")


def test_supabase_webhook_reservation_is_atomic(repository):
    assert repository.reserve_webhook("synthetic-event") is True
    assert repository.reserve_webhook("synthetic-event") is False


def test_supabase_intake_session_is_idempotent_and_stores_only_safe_correlation(
    repository,
    table_client,
):
    first = IntakeSession(
        intake_session_id=uuid4(),
        job_id=uuid4(),
        provider_call_key_hash="a" * 64,
        expected_agent_id="synthetic-intake-agent",
        agent_config_version="2026-07-19.1",
        status=IntakeSessionStatus.PENDING,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    created = repository.create_intake_session(first)
    assert created == first
    assert created is not first
    assert repository.get_intake_session(first.intake_session_id) == first
    assert repository.find_intake_session_by_provider_call_key_hash("a" * 64) == first

    replay_candidate = first.model_copy(
        update={"intake_session_id": uuid4(), "job_id": uuid4()},
        deep=True,
    )
    assert repository.create_intake_session(replay_candidate) == first

    different = first.model_copy(
        update={
            "intake_session_id": uuid4(),
            "job_id": uuid4(),
            "provider_call_key_hash": "b" * 64,
        },
        deep=True,
    )
    assert repository.create_intake_session(different) == different

    in_progress = first.model_copy(
        update={
            "status": IntakeSessionStatus.IN_PROGRESS,
            "conversation_id": "synthetic-conversation",
        },
        deep=True,
    )
    assert repository.save_intake_session(in_progress) == in_progress
    assert (
        repository.find_intake_session_by_conversation_id("synthetic-conversation") == in_progress
    )

    row = table_client.tables["intake_sessions"][str(first.intake_session_id)]
    assert set(row) == {
        "id",
        "reserved_job_id",
        "provider_call_key_hash",
        "conversation_id",
        "expected_agent_id",
        "agent_config_version",
        "status",
        "failure_code",
        "created_at",
        "updated_at",
        "completed_at",
    }
    assert row["reserved_job_id"] == str(first.job_id)
    assert row["provider_call_key_hash"] == "a" * 64
    assert row["conversation_id"] == "synthetic-conversation"
    serialized = repr(table_client.tables["intake_sessions"])
    for forbidden in (
        "CA-synthetic-provider-call",
        "+15550102001",
        "+15550102002",
        "caller_id",
        "called_number",
    ):
        assert forbidden not in serialized


def test_supabase_intake_session_rejects_identity_and_terminal_state_mutation(
    repository,
):
    pending = IntakeSession(
        intake_session_id=uuid4(),
        job_id=uuid4(),
        expected_agent_id="synthetic-intake-agent",
        agent_config_version="2026-07-19.1",
        status=IntakeSessionStatus.PENDING,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    repository.create_intake_session(pending)

    with pytest.raises(DomainConflict, match="identity"):
        repository.save_intake_session(pending.model_copy(update={"job_id": uuid4()}, deep=True))

    failed = pending.model_copy(
        update={"status": IntakeSessionStatus.FAILED},
        deep=True,
    )
    repository.save_intake_session(failed)
    with pytest.raises(DomainConflict, match="terminal"):
        repository.save_intake_session(
            failed.model_copy(update={"status": IntakeSessionStatus.PENDING}, deep=True)
        )


def test_supabase_events_are_safe_and_exclude_raw_transcript_fields(
    repository,
    table_client,
    confirmed_record,
):
    repository.create(confirmed_record)
    event = JobEvent(
        job_id=confirmed_record.job_spec.job_id,
        event_type="post_call_transcription",
        occurred_at=FIXED_NOW,
        metadata={
            "provider_status": "done",
            "transcript": "raw transcript must never persist",
            "phone_number": "+1-202-555-0100",
        },
    )

    saved = repository.append_event(event)

    assert saved.metadata == {"provider_status": "done"}
    assert repository.list_events(event.job_id) == [saved]
    serialized = repr(table_client.tables["event_log"])
    assert "raw transcript" not in serialized
    assert "+1-202" not in serialized


def test_verified_competitor_enforces_every_safety_predicate(
    repository,
    confirmed_record,
    fixtures,
    monkeypatch,
):
    repository.create(confirmed_record)
    quotes = [
        quote.model_copy(update={"job_id": confirmed_record.job_spec.job_id})
        for quote in fixtures.load_initial_quotes()
    ]
    for quote in quotes:
        repository.save_quote(quote)

    selected = repository.get_verified_competing_quote(
        confirmed_record.job_spec.job_id,
        target_vendor_id=quotes[2].vendor.vendor_id,
        job_spec_version="1.0",
    )
    assert selected is not None
    assert selected.vendor.slug == "clearpath-movers"

    unsafe_variants = (
        quotes[0].model_copy(update={"transcript_evidence": []}),
        quotes[0].model_copy(update={"verified_data": {}}),
        quotes[0].model_copy(update={"verification_status": VerificationStatus.PROVISIONAL}),
        quotes[0].model_copy(update={"manually_fabricated": True}),
        quotes[0].model_copy(update={"comparable_total": None, "negotiated_total": None}),
    )
    for unsafe in unsafe_variants:
        monkeypatch.setattr(
            repository,
            "list_quotes",
            lambda _job_id, quote=unsafe: [quote],
        )
        assert (
            repository.get_verified_competing_quote(
                confirmed_record.job_spec.job_id,
                target_vendor_id=quotes[2].vendor.vendor_id,
                job_spec_version="1.0",
            )
            is None
        )

    monkeypatch.setattr(repository, "list_quotes", lambda _job_id: [quotes[0]])
    assert (
        repository.get_verified_competing_quote(
            confirmed_record.job_spec.job_id,
            target_vendor_id=quotes[0].vendor.vendor_id,
            job_spec_version="1.0",
        )
        is None
    )
    assert (
        repository.get_verified_competing_quote(
            confirmed_record.job_spec.job_id,
            target_vendor_id=quotes[2].vendor.vendor_id,
            job_spec_version="unsupported-version",
        )
        is None
    )


def test_supabase_transport_failure_never_falls_back(
    repository,
    table_client,
    confirmed_record,
):
    repository.create(confirmed_record)
    table_client.failure = ProviderRequestError("Supabase request failed")

    with pytest.raises(ProviderRequestError, match="Supabase request failed"):
        repository.get(confirmed_record.job_spec.job_id)


def test_supabase_reset_is_never_destructive(repository, table_client):
    with pytest.raises(RuntimeError, match="disabled"):
        repository.reset()
    assert not any(operation[0] == "delete" for operation in table_client.operations)
