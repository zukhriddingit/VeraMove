"""Repository-contract tests for persistent Supabase storage."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from services.api.app.contracts import (
    CallRecord,
    CallStatus,
    ConsentMethod,
    DataClassification,
    IntakeSource,
    JobRecord,
    JobState,
    JobVendorResearchV1,
    ProvenanceReference,
    ProvenanceType,
    SuppressionReason,
    VendorCallAuthorizationV1,
    VendorSearchQuery,
    VendorSuppressionV1,
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
    job_spec_sha256,
)
from services.api.app.repositories.base import (
    VoiceIntakeCompletion,
    VoiceIntakeFailure,
    VoiceIntakeIncomplete,
    VoiceWebhookLease,
    VoiceWebhookMaterialization,
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
                "vendor_research",
                "vendor_call_authorizations",
                "vendor_call_suppressions",
            )
        }
        self.operations: list[tuple[str, str, dict[str, Any]]] = []
        self.failure: Exception | None = None
        self.rpc_responses: dict[str, dict[str, Any]] = {
            "veramove_claim_voice_webhook_receipt": {
                "claimed": True,
                "processed": False,
            },
            "veramove_fail_voice_webhook_receipt": {
                "failed": True,
                "retryable": True,
            },
            "veramove_finalize_voice_webhook": {
                "processed": True,
                "duplicate": False,
            },
            "veramove_finalize_voice_intake_webhook": {
                "processed": True,
                "duplicate": False,
            },
            "veramove_claim_intake_resume": {},
            "veramove_finish_intake_manually": {},
        }

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

    def rpc(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._maybe_fail()
        self.operations.append(("rpc", name, deepcopy(payload)))
        return deepcopy(self.rpc_responses[name])

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


def test_supabase_vendor_research_round_trip_uses_separate_table(
    repository,
    table_client,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    candidates = [
        vendor.model_copy(
            update={"data_classification": DataClassification.REAL_REDACTED},
            deep=True,
        )
        for vendor in fixtures.load_vendors()
    ]
    research = JobVendorResearchV1(
        job_id=confirmed_record.job_spec.job_id,
        job_spec_version=confirmed_record.job_spec.version,
        query=VendorSearchQuery(city="Newton", state="MA"),
        candidates=candidates,
        source="tavily",
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )

    saved = repository.save_vendor_research(research)
    saved.candidates.clear()
    loaded = repository.get_vendor_research(
        confirmed_record.job_spec.job_id,
        confirmed_record.job_spec.version,
    )

    assert loaded is not None
    assert len(loaded.candidates) == 3
    assert len(table_client.tables["vendor_research"]) == 1
    row = next(iter(table_client.tables["vendor_research"].values()))
    assert row["job_id"] == str(confirmed_record.job_spec.job_id)
    assert row["job_spec_version"] == "1.0"
    assert row["data_classification"] == "real_redacted"
    assert "calls" not in row["payload"]
    assert "quotes" not in row["payload"]


def test_supabase_vendor_authorization_and_suppression_are_server_only(
    repository,
    table_client,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    vendor = fixtures.load_vendors()[0]
    authorization = VendorCallAuthorizationV1(
        job_id=confirmed_record.job_spec.job_id,
        job_spec_version=confirmed_record.job_spec.version,
        job_spec_sha256=job_spec_sha256(confirmed_record.job_spec),
        vendor_id=vendor.vendor_id,
        contact_id=uuid4(),
        normalized_number="+16175550101",
        display_number="(617) 555-0101",
        number_hash="a" * 64,
        recipient_timezone="America/New_York",
        consent_method=ConsentMethod.PROVIDER_TEST_DESTINATION,
        consent_evidence_reference="consent:synthetic:001",
        consented_at=FIXED_NOW,
        ai_call_consented=True,
        recording_consented=True,
        source_url="https://vendor.example/contact",
        created_at=FIXED_NOW,
    )
    suppression = VendorSuppressionV1(
        number_hash=authorization.number_hash,
        reason=SuppressionReason.MANUAL_BLOCK,
        created_at=FIXED_NOW,
    )

    assert repository.save_vendor_call_authorization(authorization) == authorization
    assert repository.get_vendor_call_authorization(
        authorization.job_id,
        authorization.job_spec_version,
        authorization.vendor_id,
    ) == authorization
    assert repository.list_vendor_call_authorizations(
        authorization.job_id,
        authorization.job_spec_version,
    ) == [authorization]
    assert repository.save_vendor_suppression(suppression) == suppression
    assert repository.get_vendor_suppression(authorization.number_hash) == suppression
    row = table_client.tables["vendor_call_authorizations"][
        str(authorization.authorization_id)
    ]
    assert row["normalized_number"] == "+16175550101"
    assert "normalized_number" not in authorization.model_dump(mode="json")


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


def test_supabase_voice_receipt_adapters_use_validated_rpc_payloads(
    repository,
    table_client,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    attempt = make_attempt(confirmed_record, fixtures.load_vendors()[0])
    repository.create_attempt(attempt)
    result = MockVoiceProvider(fixtures).initiate_quote_call(
        confirmed_record.job_spec,
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
            "provider_version_id": "synthetic-version",
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
    quote = result.outcome.quote
    job = confirmed_record.model_copy(
        update={
            "state": JobState.CALLING,
            "calls": [call],
            "quotes": [quote],
            "updated_at": result.completed_at,
        },
        deep=True,
    )
    event = JobEvent(
        job_id=attempt.job_id,
        call_id=attempt.call_id,
        event_type="post_call_transcription",
        occurred_at=result.completed_at,
        metadata={"provider_status": "done"},
    )
    materialization = VoiceWebhookMaterialization(
        attempt=completed_attempt,
        call=call,
        quote=quote,
        job=job,
        event=event,
        expected_revision=repository.get_job_revision(attempt.job_id),
    )
    now = datetime(2026, 7, 19, 2, 0, tzinfo=UTC)
    token = uuid4()
    lease = VoiceWebhookLease(
        idempotency_key="synthetic-supabase-voice-event",
        event_type="post_call_transcription",
        lease_token=token,
        lease_expires_at=now + timedelta(minutes=5),
        now=now,
    )

    assert repository.claim_voice_webhook_receipt(lease).claimed is True
    assert repository.fail_voice_webhook_receipt(
        lease.idempotency_key,
        token,
        "transient_storage",
        True,
        now,
    ).retryable is True
    assert repository.finalize_voice_webhook(
        lease.idempotency_key,
        token,
        materialization,
        now,
    ).duplicate is False

    rpc_operations = [item for item in table_client.operations if item[0] == "rpc"]
    assert [item[1] for item in rpc_operations] == [
        "veramove_claim_voice_webhook_receipt",
        "veramove_fail_voice_webhook_receipt",
        "veramove_finalize_voice_webhook",
    ]
    finalize_payload = rpc_operations[-1][2]
    assert set(finalize_payload) == {
        "p_idempotency_key",
        "p_lease_token",
        "p_attempt",
        "p_call",
        "p_quote",
        "p_evidence",
        "p_job",
        "p_event",
        "p_now",
    }
    assert finalize_payload["p_job"]["expected_revision"] == 0
    assert finalize_payload["p_attempt"]["destination_slot"] == 0
    assert finalize_payload["p_attempt"]["job_spec_sha256"] == attempt.job_spec_sha256
    serialized = repr(finalize_payload).lower()
    for forbidden in (
        "raw_body",
        "raw_payload",
        "full transcript",
        "+15550100001",
        "api_key",
        "synthetic-supabase-secret",
        "audio_bytes",
    ):
        assert forbidden not in serialized


def test_supabase_voice_intake_finalizer_uses_one_safe_typed_rpc(
    repository,
    table_client,
    confirmed_record,
):
    now = datetime(2026, 7, 19, 2, 30, tzinfo=UTC)
    session = IntakeSession(
        intake_session_id=uuid4(),
        job_id=confirmed_record.job_spec.job_id,
        expected_agent_id="synthetic-intake-agent",
        agent_config_version="2026-07-19.1",
        status=IntakeSessionStatus.IN_PROGRESS,
        conversation_id="synthetic-intake-conversation",
        created_at=now - timedelta(minutes=1),
        updated_at=now - timedelta(minutes=1),
    )
    repository.create_intake_session(session)
    completed_session = session.model_copy(
        update={
            "status": IntakeSessionStatus.COMPLETED,
            "updated_at": now,
            "completed_at": now,
        },
        deep=True,
    )
    voice_spec = confirmed_record.job_spec.model_copy(
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
    event = JobEvent(
        job_id=session.job_id,
        event_type="post_call_transcription",
        occurred_at=now,
        metadata={"provider_status": "done"},
    )
    completion = VoiceIntakeCompletion(
        session=completed_session,
        job=job,
        event=event,
    )
    token = uuid4()

    assert repository.finalize_voice_intake_webhook(
        "synthetic-intake-completion-event",
        token,
        completion,
        now,
    ).duplicate is False

    completion_rpc = table_client.operations[-1]
    assert completion_rpc[:2] == (
        "rpc",
        "veramove_finalize_voice_intake_webhook",
    )
    completion_payload = completion_rpc[2]
    assert set(completion_payload) == {
        "p_idempotency_key",
        "p_lease_token",
        "p_schema_version",
        "p_kind",
        "p_session",
        "p_job",
        "p_event",
        "p_now",
    }
    assert completion_payload["p_kind"] == "completed"
    assert completion_payload["p_session"]["status"] == "completed"
    assert completion_payload["p_job"]["state"] == "intake_complete"
    assert completion_payload["p_event"]["idempotency_key"] == (
        "synthetic-intake-completion-event"
    )

    failure_session = IntakeSession(
        intake_session_id=uuid4(),
        job_id=uuid4(),
        expected_agent_id="synthetic-intake-agent",
        agent_config_version="2026-07-19.1",
        status=IntakeSessionStatus.IN_PROGRESS,
        conversation_id="synthetic-failed-intake-conversation",
        created_at=now - timedelta(minutes=1),
        updated_at=now - timedelta(minutes=1),
    )
    repository.create_intake_session(failure_session)
    failure = VoiceIntakeFailure(
        session=failure_session.model_copy(
            update={
                "status": IntakeSessionStatus.FAILED,
                "failure_code": "provider_no_answer",
                "updated_at": now,
            },
            deep=True,
        ),
        event_type="call_initiation_failure",
    )
    repository.finalize_voice_intake_webhook(
        "synthetic-intake-failure-event",
        token,
        failure,
        now,
    )
    failure_payload = table_client.operations[-1][2]
    assert failure_payload["p_kind"] == "failed"
    assert failure_payload["p_job"] is None
    assert failure_payload["p_event"] == {"event_type": "call_initiation_failure"}

    serialized = repr(completion_payload) + repr(failure_payload)
    for forbidden in (
        "'transcript':",
        "'analysis':",
        "'phone_number':",
        "+15550100001",
        "'audio':",
        "'api_key':",
    ):
        assert forbidden not in serialized.lower()


def test_supabase_voice_intake_finalizer_serializes_incomplete_without_job(
    repository,
    table_client,
    job_spec,
):
    now = datetime(2026, 7, 19, 2, 30, tzinfo=UTC)
    session = IntakeSession(
        job_id=job_spec.job_id,
        expected_agent_id="synthetic-intake-agent",
        agent_config_version="2026-07-21.2",
        status=IntakeSessionStatus.IN_PROGRESS,
        conversation_id="synthetic-incomplete-conversation",
        created_at=now - timedelta(minutes=1),
        updated_at=now - timedelta(minutes=1),
    )
    repository.create_intake_session(session)
    partial = job_spec.model_copy(
        update={
            "intake_source": IntakeSource.VOICE,
            "move_date": None,
            "confirmed": False,
            "confirmed_at": None,
            "locked_version": None,
            "data_classification": DataClassification.ROLE_PLAY,
        },
        deep=True,
    )
    incomplete = VoiceIntakeIncomplete(
        session=session.model_copy(
            update={
                "status": IntakeSessionStatus.INCOMPLETE,
                "partial_job_spec": partial,
                "missing_fields": tuple(partial.missing_required_fields()),
                "terminal_reason": "user_ended_before_summary",
                "updated_at": now,
            },
            deep=True,
        ),
        event_type="post_call_transcription",
    )

    repository.finalize_voice_intake_webhook(
        "synthetic-intake-incomplete-event",
        uuid4(),
        incomplete,
        now,
    )

    payload = table_client.operations[-1][2]
    assert payload["p_kind"] == "incomplete"
    assert payload["p_job"] is None
    assert payload["p_session"]["status"] == "incomplete"
    assert payload["p_session"]["partial_job_spec"]["move_date"] is None
    assert "'transcript':" not in repr(payload).lower()


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
        "data_mode",
        "status",
        "partial_job_spec",
        "base_job_spec",
        "missing_fields",
        "terminal_reason",
        "recovery_action",
        "recovery_target_id",
        "resumed_from_session_id",
        "failure_code",
        "created_at",
        "updated_at",
        "completed_at",
        "browser_credential_issued_at",
    }
    assert row["reserved_job_id"] == str(first.job_id)
    assert row["provider_call_key_hash"] == "a" * 64
    assert row["conversation_id"] == "synthetic-conversation"
    assert row["browser_credential_issued_at"] is None
    serialized = repr(table_client.tables["intake_sessions"])
    for forbidden in (
        "CA-synthetic-provider-call",
        "+15550102001",
        "+15550102002",
        "caller_id",
        "called_number",
    ):
        assert forbidden not in serialized


def test_supabase_reserves_browser_credential_through_atomic_rpc(
    repository,
    table_client,
) -> None:
    session = IntakeSession(
        expected_agent_id="agent_synthetic_intake",
        agent_config_version="2026-07-19.browser-v1",
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    reserved_session = session.model_copy(
        update={"browser_credential_issued_at": FIXED_NOW},
        deep=True,
    )
    table_client.rpc_responses["veramove_reserve_browser_voice_credential"] = (
        repository._intake_session_row(reserved_session)
    )

    reserved = repository.reserve_intake_browser_credential(
        session.intake_session_id,
        FIXED_NOW,
    )

    assert reserved.browser_credential_issued_at == FIXED_NOW
    assert table_client.operations[-1] == (
        "rpc",
        "veramove_reserve_browser_voice_credential",
        {
            "p_session_id": str(session.intake_session_id),
            "p_issued_at": FIXED_NOW.isoformat(),
        },
    )


def test_supabase_resume_and_manual_finish_use_atomic_typed_rpcs(
    repository,
    table_client,
    job_spec,
) -> None:
    now = FIXED_NOW
    resume_job_id = uuid4()
    partial = job_spec.model_copy(
        update={
            "job_id": resume_job_id,
            "intake_source": IntakeSource.VOICE,
            "move_date": None,
            "data_classification": DataClassification.ROLE_PLAY,
            "confirmed": False,
            "confirmed_at": None,
            "locked_version": None,
        },
        deep=True,
    )
    source = IntakeSession(
        job_id=resume_job_id,
        expected_agent_id="synthetic-intake-agent",
        agent_config_version="2026-07-21.2",
        status=IntakeSessionStatus.INCOMPLETE,
        conversation_id="synthetic-resume-source",
        partial_job_spec=partial,
        missing_fields=partial.missing_required_fields(),
        terminal_reason="user_ended_before_summary",
        created_at=now - timedelta(minutes=1),
        updated_at=now,
    )
    repository.create_intake_session(source)
    child_job_id = uuid4()
    child = IntakeSession(
        job_id=child_job_id,
        expected_agent_id=source.expected_agent_id,
        agent_config_version=source.agent_config_version,
        data_mode=source.data_mode,
        base_job_spec=partial.model_copy(
            update={"job_id": child_job_id},
            deep=True,
        ),
        resumed_from_session_id=source.intake_session_id,
        created_at=now,
        updated_at=now,
    )
    table_client.rpc_responses["veramove_claim_intake_resume"] = (
        repository._intake_session_row(child)
    )

    assert repository.claim_intake_resume(source.intake_session_id, child, now) == child
    resume_rpc = table_client.operations[-1]
    assert resume_rpc[:2] == ("rpc", "veramove_claim_intake_resume")
    assert resume_rpc[2]["p_child"]["base_job_spec"]["job_id"] == str(child_job_id)

    manual_job_id = uuid4()
    manual_partial = partial.model_copy(update={"job_id": manual_job_id}, deep=True)
    manual_source = source.model_copy(
        update={
            "intake_session_id": uuid4(),
            "job_id": manual_job_id,
            "conversation_id": "synthetic-manual-source",
            "partial_job_spec": manual_partial,
        },
        deep=True,
    )
    repository.create_intake_session(manual_source)
    manual_job = JobRecord(
        job_spec=manual_partial,
        state=JobState.INTAKE_COMPLETE,
        created_at=now,
        updated_at=now,
    )
    table_client.rpc_responses["veramove_finish_intake_manually"] = (
        repository._job_row(manual_job)
    )

    assert (
        repository.finish_intake_manually(
            manual_source.intake_session_id,
            manual_job,
            now,
        )
        == manual_job
    )
    manual_rpc = table_client.operations[-1]
    assert manual_rpc[:2] == ("rpc", "veramove_finish_intake_manually")
    serialized = repr(resume_rpc[2]) + repr(manual_rpc[2])
    assert "'transcript':" not in serialized.lower()
    assert "phone_number" not in serialized.lower()


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
        update={
            "status": IntakeSessionStatus.FAILED,
            "failure_code": "synthetic_failure",
        },
        deep=True,
    )
    repository.save_intake_session(failed)
    with pytest.raises(DomainConflict, match="terminal"):
        repository.save_intake_session(
            failed.model_copy(
                update={
                    "status": IntakeSessionStatus.PENDING,
                    "failure_code": None,
                },
                deep=True,
            )
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
