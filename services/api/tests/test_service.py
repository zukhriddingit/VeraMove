"""Application-service workflow tests."""

import pytest

from services.api.app.contracts import JobState
from services.api.app.core.errors import DomainConflict, InvalidStateTransition


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
    assert len(completed.quotes) == 4
    assert completed.quotes[-1].negotiated_total < completed.quotes[-1].original_total

    report = service.get_report(job_spec.job_id)
    assert report.rankings[0].evidence_ids
    assert report.rankings[0].vendor.slug == "clearpath-movers"
    assert len(report.transcript_evidence) == 4
    assert all(
        str(evidence.recording_url).startswith("https://recordings.example.com/")
        for evidence in report.transcript_evidence
    )


def test_confirmation_locks_state(service, job_spec):
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)
    with pytest.raises(InvalidStateTransition):
        service.confirm_job(job_spec.job_id)


def test_calls_require_confirmation(service, job_spec):
    service.create_job(job_spec)
    with pytest.raises(InvalidStateTransition, match="intake_complete -> calling"):
        service.start_calls(job_spec.job_id)


def test_report_requires_completed_negotiation(service, job_spec):
    service.create_job(job_spec)
    with pytest.raises(DomainConflict, match="only after negotiation"):
        service.get_report(job_spec.job_id)
