"""Repository and mock adapter boundary tests."""

from datetime import UTC, datetime
from uuid import uuid4

from services.api.app.contracts import (
    CallOutcomeType,
    CallStatus,
    JobRecord,
    JobState,
    VerificationStatus,
)
from services.api.app.integrations.elevenlabs.mock import (
    MockTwilioTransport,
    MockVoiceVendorGateway,
)
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.orchestration.models import (
    CallAttempt,
    CallKind,
    JobEvent,
    VoiceCallReference,
)
from services.api.app.repositories.memory import InMemoryRepository


def make_confirmed_record(job_spec) -> JobRecord:
    confirmed_at = datetime.now(UTC)
    confirmed_spec = job_spec.model_copy(
        update={"confirmed": True, "confirmed_at": confirmed_at},
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
    call = MockVoiceVendorGateway(fixtures).create_calls(record.job_spec)[0]
    quote = call.outcome.quote
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


def test_verified_competitor_excludes_target_and_unverified_quotes(fixtures, job_spec):
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

    repository.save_quote(
        quotes[0].model_copy(
            update={"job_id": job_spec.job_id, "transcript_evidence": []},
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


def test_mock_voice_gateway_returns_three_itemized_calls(fixtures, job_spec):
    calls = MockVoiceVendorGateway(fixtures).create_calls(job_spec)
    assert len(calls) == 3
    assert all(call.outcome.type is CallOutcomeType.ITEMIZED_QUOTE for call in calls)
    assert all(call.outcome.quote is not None for call in calls)
    assert all(
        call.outcome.quote.provisional_data["twilio_transport_reference"].startswith(
            "synthetic-twilio-"
        )
        for call in calls
        if call.outcome.quote is not None
    )


def test_mock_twilio_transport_never_requires_a_phone_number(fixtures, job_spec):
    vendor = fixtures.load_vendors()[0]
    reference = MockTwilioTransport().create_call_reference(vendor, job_spec)
    assert reference.endswith("clearpath-movers")
    assert reference.startswith("synthetic-twilio-")


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
