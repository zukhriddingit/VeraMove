"""Repository and mock adapter boundary tests."""

from datetime import UTC, datetime

import pytest

from services.api.app.contracts import CallOutcomeType, JobRecord, JobState, VerificationStatus
from services.api.app.core.errors import DomainConflict
from services.api.app.integrations.elevenlabs.mock import (
    MockTwilioTransport,
    MockVoiceVendorGateway,
)
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.repositories.memory import InMemoryJobRepository


def test_repository_returns_defensive_copy(job_spec):
    repository = InMemoryJobRepository()
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


def test_webhook_idempotency_is_process_local():
    repository = InMemoryJobRepository()
    assert repository.record_webhook("synthetic-event-1", {}) is True
    assert repository.record_webhook("synthetic-event-1", {}) is False


def test_repository_rejects_changes_to_locked_job_spec(job_spec):
    repository = InMemoryJobRepository()
    now = datetime.now(UTC)
    confirmed = job_spec.model_copy(
        update={"confirmed": True, "confirmed_at": now, "locked_version": "1.0"}
    )
    record = JobRecord(
        job_spec=confirmed,
        state=JobState.CONFIRMED,
        created_at=now,
        updated_at=now,
    )
    repository.create(record)
    record.job_spec = record.job_spec.model_copy(update={"bedroom_count": 3})
    with pytest.raises(DomainConflict, match="locked"):
        repository.save(record)


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
