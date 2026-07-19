"""Application-service workflow tests."""

import pytest

from services.api.app.contracts import CallStatus, IntakeSource, JobState
from services.api.app.core.errors import DomainConflict, InvalidStateTransition


class StaticDiscoveryGateway:
    source = "tavily"

    def __init__(self, vendors):
        self._vendors = vendors

    def discover(self, origin, destination):
        del origin, destination
        return [vendor.model_copy(deep=True) for vendor in self._vendors]

    def source_call_list(self, query):
        del query
        return [vendor.model_copy(deep=True) for vendor in self._vendors]


def test_mock_workflow(service, job_spec):
    created = service.create_job(job_spec)
    assert created.state is JobState.INTAKE_COMPLETE

    confirmed = service.confirm_job(job_spec.job_id)
    assert confirmed.state is JobState.CONFIRMED
    assert confirmed.job_spec.confirmed is True
    assert confirmed.job_spec.confirmed_at is not None

    called = service.start_calls(job_spec.job_id)
    assert called.state is JobState.QUOTES_READY
    assert len(called.calls) == 3
    assert len(called.quotes) == 3

    completed = service.negotiate(job_spec.job_id)
    assert completed.state is JobState.COMPLETED
    assert len(completed.calls) == 4
    assert len(completed.quotes) == 4
    assert completed.quotes[-1].negotiated_total < completed.quotes[-1].original_total

    repeated = service.negotiate(job_spec.job_id)
    assert repeated == completed
    assert len(service.list_call_attempts(job_spec.job_id)) == 4

    report = service.get_report(job_spec.job_id)
    assert report.rankings[0].evidence_ids
    assert report.rankings[0].vendor.slug == "clearpath-movers"
    assert len(report.transcript_evidence) == 4
    assert all(
        str(evidence.recording_url).startswith("https://recordings.example.com/")
        for evidence in report.transcript_evidence
    )
    stored_evidence = {
        evidence.evidence_id: evidence
        for quote in completed.quotes
        for evidence in quote.transcript_evidence
    }
    assert {item.evidence_id: item for item in report.transcript_evidence} == stored_evidence


def test_confirmation_is_idempotent_and_defensive(service, job_spec):
    service.create_job(job_spec)
    first = service.confirm_job(job_spec.job_id)
    second = service.confirm_job(job_spec.job_id)
    assert second == first

    first.job_spec.origin.address_summary = "Mutated outside repository"
    stored = service.get_job(job_spec.job_id)
    assert stored.job_spec.origin.address_summary != "Mutated outside repository"


def test_document_intake_creates_fresh_document_job(service, job_spec):
    created = service.create_job_from_document("Synthetic inventory document.")

    assert created.job_spec.job_id != job_spec.job_id
    assert created.job_spec.intake_source is IntakeSource.DOCUMENT
    assert created.state is JobState.INTAKE_COMPLETE


def test_single_quote_call_persists_attempt_before_canonical_result(
    service,
    fixtures,
    job_spec,
):
    service.create_job(job_spec)
    confirmed = service.confirm_job(job_spec.job_id)

    attempt = service.initiate_single_quote_call(
        job_spec.job_id,
        fixtures.load_vendors()[0],
    )

    assert attempt.status is CallStatus.COMPLETED
    assert attempt.reference is not None
    assert attempt.job_spec_snapshot == confirmed.job_spec
    stored = service.get_job(job_spec.job_id)
    assert len(stored.calls) == 1
    assert len(stored.quotes) == 1


def test_batch_uses_exact_confirmed_snapshot_and_does_not_redial(
    service,
    job_spec,
):
    service.create_job(job_spec)
    confirmed = service.confirm_job(job_spec.job_id)

    first = service.initiate_quote_batch(job_spec.job_id)
    second = service.initiate_quote_batch(job_spec.job_id)

    assert first == second
    assert first.state is JobState.QUOTES_READY
    assert len(first.calls) == 3
    attempts = service.list_call_attempts(job_spec.job_id)
    assert len(attempts) == 3
    assert all(item.job_spec_snapshot == confirmed.job_spec for item in attempts)
    assert len({item.call_id for item in attempts}) == 3


def test_batch_uses_first_three_distinct_discovery_vendors(
    service,
    fixtures,
    job_spec,
):
    discovery_vendors = list(reversed(fixtures.load_vendors()))
    service._discovery = StaticDiscoveryGateway(discovery_vendors)
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)

    result = service.start_calls(job_spec.job_id)

    assert len(result.calls) == 3
    assert [call.vendor.vendor_id for call in result.calls] == [
        vendor.vendor_id for vendor in discovery_vendors[:3]
    ]


def test_batch_rejects_short_distinct_discovery_before_state_or_call_side_effects(
    service,
    fixtures,
    job_spec,
):
    vendors = fixtures.load_vendors()
    service._discovery = StaticDiscoveryGateway(
        [vendors[0], vendors[1], vendors[1]],
    )
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)

    with pytest.raises(DomainConflict, match="three distinct vendors"):
        service.start_calls(job_spec.job_id)

    stored = service.get_job(job_spec.job_id)
    assert stored.state is JobState.CONFIRMED
    assert stored.calls == []
    assert stored.quotes == []
    assert service.list_call_attempts(job_spec.job_id) == []


def test_mock_service_reports_truthful_vendor_discovery_source(service):
    assert service.vendor_discovery_source == "synthetic_mock"


def test_batch_completes_remaining_vendors_after_single_call(
    service,
    fixtures,
    job_spec,
):
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)
    service.initiate_single_quote_call(job_spec.job_id, fixtures.load_vendors()[0])

    called = service.initiate_quote_batch(job_spec.job_id)

    assert called.state is JobState.QUOTES_READY
    assert len(called.calls) == 3
    assert len(service.list_call_attempts(job_spec.job_id)) == 3


def test_calls_require_confirmation(service, job_spec):
    service.create_job(job_spec)
    with pytest.raises(InvalidStateTransition, match="intake_complete -> calling"):
        service.start_calls(job_spec.job_id)


def test_confirmation_rejects_incomplete_job_spec_without_changing_state(
    service,
    job_spec,
):
    incomplete = job_spec.model_copy(update={"move_date": None})
    service.create_job(incomplete)
    with pytest.raises(DomainConflict, match="move_date"):
        service.confirm_job(incomplete.job_id)
    assert service.get_job(incomplete.job_id).state is JobState.INTAKE_COMPLETE


def test_report_requires_completed_negotiation(service, job_spec):
    service.create_job(job_spec)
    with pytest.raises(DomainConflict, match="only after negotiation"):
        service.get_report(job_spec.job_id)
