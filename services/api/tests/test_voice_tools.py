"""Voice-provider and tool-facade safety tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from services.api.app.contracts import (
    CallOutcome,
    CallOutcomeType,
    CallStatus,
    IntakeSource,
    JobRecord,
    JobState,
    VerificationStatus,
)
from services.api.app.core.errors import DomainConflict, ResourceNotFound
from services.api.app.integrations.elevenlabs.mock import MockVoiceProvider
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.orchestration.mock_intelligence import MockIntelligenceProvider
from services.api.app.orchestration.models import CallAttempt, CallKind
from services.api.app.orchestration.tools import VoiceTools
from services.api.app.repositories.memory import InMemoryRepository


def make_confirmed_record(job_spec) -> JobRecord:
    confirmed_at = datetime(2026, 7, 18, 16, 0, tzinfo=UTC)
    return JobRecord(
        job_spec=job_spec.model_copy(
            update={
                "confirmed": True,
                "confirmed_at": confirmed_at,
                "locked_version": job_spec.version,
            },
            deep=True,
        ),
        state=JobState.CONFIRMED,
        created_at=confirmed_at,
        updated_at=confirmed_at,
    )


def make_attempt(job_spec, vendor) -> CallAttempt:
    return CallAttempt(
        call_id=uuid4(),
        job_id=job_spec.job_id,
        kind=CallKind.QUOTE,
        vendor=vendor,
        job_spec_snapshot=job_spec.model_copy(deep=True),
        status=CallStatus.PENDING,
        started_at=datetime(2026, 7, 18, 16, 30, tzinfo=UTC),
    )


@pytest.fixture
def repository() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def confirmed_record(job_spec) -> JobRecord:
    return make_confirmed_record(job_spec)


def test_mock_voice_provider_initiates_one_quote_call(fixtures, job_spec):
    provider = MockVoiceProvider(fixtures)
    vendor = fixtures.load_vendors()[0]
    call_id = uuid4()

    result = provider.initiate_quote_call(job_spec, vendor, call_id)

    assert provider.initial_call_limit == 3
    assert result.outcome is not None
    assert result.outcome.type is CallOutcomeType.ITEMIZED_QUOTE
    assert result.outcome.quote is not None
    assert result.outcome.quote.vendor == vendor
    assert result.outcome.quote.job_id == job_spec.job_id
    assert result.outcome.quote.job_spec_version == job_spec.version
    assert all(
        evidence.call_id == call_id
        for evidence in result.outcome.quote.transcript_evidence
    )


def test_mock_voice_provider_rebinds_negotiated_quote(fixtures, job_spec):
    provider = MockVoiceProvider(fixtures)
    target = fixtures.load_vendors()[2]
    competitor = fixtures.load_initial_quotes()[0].model_copy(
        update={"job_id": job_spec.job_id},
        deep=True,
    )
    planned = fixtures.load_negotiated_quote()
    call_id = uuid4()

    result = provider.initiate_negotiation_call(
        job_spec,
        target,
        competitor,
        planned,
        call_id,
    )

    assert result.outcome is not None
    assert result.outcome.quote is not None
    assert result.outcome.quote.job_id == job_spec.job_id
    assert result.outcome.quote.job_spec_version == job_spec.version
    assert result.outcome.quote.vendor == target
    assert all(
        evidence.call_id == call_id
        for evidence in result.outcome.quote.transcript_evidence
    )


def test_mock_intelligence_extracts_document_as_fresh_unconfirmed_job(fixtures, job_spec):
    provider = MockIntelligenceProvider(
        fixtures,
        MockNegotiationGateway(fixtures),
    )

    extracted = provider.extract_document("Synthetic inventory document for the demo.")

    assert extracted.job_id != job_spec.job_id
    assert extracted.intake_source is IntakeSource.DOCUMENT
    assert extracted.confirmed is False
    assert extracted.confirmed_at is None
    assert extracted.locked_version is None


def test_mock_intelligence_rejects_blank_document(fixtures):
    provider = MockIntelligenceProvider(
        fixtures,
        MockNegotiationGateway(fixtures),
    )

    with pytest.raises(DomainConflict, match="Document text is required"):
        provider.extract_document("   ")


def test_mock_intelligence_delegates_negotiation(fixtures, job_spec):
    provider = MockIntelligenceProvider(
        fixtures,
        MockNegotiationGateway(fixtures),
    )
    quotes = fixtures.load_initial_quotes()

    negotiated = provider.negotiate(job_spec, quotes, quotes[0])

    assert negotiated.negotiated_total < negotiated.original_total
    assert negotiated.verified_data["competing_quote_id"] == str(quotes[0].quote_id)


def test_tools_reject_verified_quote_without_evidence(
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    vendor = fixtures.load_vendors()[0]
    attempt = make_attempt(confirmed_record.job_spec, vendor)
    repository.create_attempt(attempt)
    quote = fixtures.load_initial_quotes()[0].model_copy(
        update={
            "job_id": confirmed_record.job_spec.job_id,
            "transcript_evidence": [],
        },
        deep=True,
    )

    with pytest.raises(DomainConflict, match="Verified quotes require evidence"):
        VoiceTools(repository, repository).save_quote(attempt.call_id, quote)


def test_tools_reject_verified_quote_without_verified_data(
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    vendor = fixtures.load_vendors()[0]
    attempt = make_attempt(confirmed_record.job_spec, vendor)
    repository.create_attempt(attempt)
    evidence = [
        item.model_copy(update={"call_id": attempt.call_id})
        for item in fixtures.load_initial_quotes()[0].transcript_evidence
    ]
    quote = fixtures.load_initial_quotes()[0].model_copy(
        update={
            "job_id": confirmed_record.job_spec.job_id,
            "verified_data": {},
            "transcript_evidence": evidence,
        },
        deep=True,
    )

    with pytest.raises(DomainConflict, match="Verified quotes require evidence"):
        VoiceTools(repository, repository).save_quote(attempt.call_id, quote)


@pytest.mark.parametrize(
    ("changed_field", "changed_value", "message"),
    [
        ("job_id", uuid4(), "Quote job does not match call attempt"),
        ("job_spec_version", "0.9", "Quote JobSpec version does not match call attempt"),
    ],
)
def test_tools_reject_cross_boundary_quotes(
    changed_field,
    changed_value,
    message,
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    attempt = make_attempt(confirmed_record.job_spec, fixtures.load_vendors()[0])
    repository.create_attempt(attempt)
    quote = fixtures.load_initial_quotes()[0].model_copy(
        update={
            "job_id": confirmed_record.job_spec.job_id,
            changed_field: changed_value,
        },
    )

    with pytest.raises(DomainConflict, match=message):
        VoiceTools(repository, repository).save_quote(attempt.call_id, quote)


def test_tools_reject_quote_from_different_vendor(
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    attempt = make_attempt(confirmed_record.job_spec, fixtures.load_vendors()[0])
    repository.create_attempt(attempt)
    quote = fixtures.load_initial_quotes()[1].model_copy(
        update={"job_id": confirmed_record.job_spec.job_id},
    )

    with pytest.raises(DomainConflict, match="Quote vendor does not match call attempt"):
        VoiceTools(repository, repository).save_quote(attempt.call_id, quote)


def test_tools_reject_evidence_from_different_call(
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    attempt = make_attempt(confirmed_record.job_spec, fixtures.load_vendors()[0])
    repository.create_attempt(attempt)
    quote = fixtures.load_initial_quotes()[0].model_copy(
        update={"job_id": confirmed_record.job_spec.job_id},
    )

    with pytest.raises(DomainConflict, match="Quote evidence does not match call attempt"):
        VoiceTools(repository, repository).save_quote(attempt.call_id, quote)


def test_tools_require_existing_call_attempt(repository, fixtures):
    quote = fixtures.load_initial_quotes()[0]

    with pytest.raises(ResourceNotFound, match="Call attempt"):
        VoiceTools(repository, repository).save_quote(uuid4(), quote)


def test_tools_store_valid_itemized_outcome_and_quote(
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    attempt = make_attempt(confirmed_record.job_spec, fixtures.load_vendors()[0])
    repository.create_attempt(attempt)
    result = MockVoiceProvider(fixtures).initiate_quote_call(
        attempt.job_spec_snapshot,
        attempt.vendor,
        attempt.call_id,
    )
    assert result.outcome is not None
    assert result.completed_at is not None
    assert result.recording_url is not None

    call = VoiceTools(repository, repository).save_call_outcome(
        attempt.call_id,
        result.outcome,
        result.completed_at,
        result.recording_url,
    )

    assert call.outcome.quote is not None
    assert repository.list_quotes(attempt.job_id) == [call.outcome.quote]
    assert repository.list_calls(attempt.job_id) == [call]


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        (
            CallOutcome(
                type=CallOutcomeType.CALLBACK_COMMITMENT,
                callback_at=datetime(2026, 7, 19, 17, 0, tzinfo=UTC),
            ),
            CallStatus.COMPLETED,
        ),
        (
            CallOutcome(
                type=CallOutcomeType.DOCUMENTED_DECLINE,
                reason="Synthetic vendor declined the service area.",
            ),
            CallStatus.COMPLETED,
        ),
        (
            CallOutcome(
                type=CallOutcomeType.FAILED,
                reason="Synthetic transport failure.",
            ),
            CallStatus.FAILED,
        ),
    ],
)
def test_tools_store_every_non_quote_outcome(
    outcome,
    expected_status,
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    attempt = make_attempt(confirmed_record.job_spec, fixtures.load_vendors()[0])
    repository.create_attempt(attempt)
    tools = VoiceTools(repository, repository)
    completed_at = datetime(2026, 7, 18, 17, 0, tzinfo=UTC)
    recording_url = "https://recordings.example.com/synthetic-outcome.mp3"

    call = tools.save_call_outcome(
        attempt.call_id,
        outcome,
        completed_at,
        recording_url,
    )
    tools.save_call_outcome(attempt.call_id, outcome, completed_at, recording_url)

    assert call.outcome == outcome
    assert call.job_id == attempt.job_id
    assert call.vendor == attempt.vendor
    assert repository.get_attempt(attempt.call_id).status is expected_status
    assert repository.list_calls(attempt.job_id) == [call]


def test_request_callback_uses_the_validated_outcome_path(
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    attempt = make_attempt(confirmed_record.job_spec, fixtures.load_vendors()[0])
    repository.create_attempt(attempt)
    completed_at = datetime(2026, 7, 18, 17, 0, tzinfo=UTC)
    callback_at = completed_at + timedelta(days=1)
    tools = VoiceTools(repository, repository, clock=lambda: completed_at)

    call = tools.request_callback(
        attempt.call_id,
        callback_at,
        "https://recordings.example.com/synthetic-callback.mp3",
    )

    assert call.outcome.type is CallOutcomeType.CALLBACK_COMMITMENT
    assert call.outcome.callback_at == callback_at
    assert call.completed_at == completed_at


def test_tools_return_only_verified_evidence_backed_competing_quote(
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    quotes = fixtures.load_initial_quotes()
    for quote in quotes:
        repository.save_quote(
            quote.model_copy(update={"job_id": confirmed_record.job_spec.job_id}),
        )

    selected = VoiceTools(repository, repository).get_verified_competing_quote(
        confirmed_record.job_spec.job_id,
        quotes[2].vendor.vendor_id,
        confirmed_record.job_spec.version,
    )

    assert selected.vendor == quotes[0].vendor


def test_tools_reject_when_verified_competing_quote_is_unavailable(
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    quote = fixtures.load_initial_quotes()[0].model_copy(
        update={
            "job_id": confirmed_record.job_spec.job_id,
            "verification_status": VerificationStatus.PARTIALLY_VERIFIED,
        },
    )
    repository.save_quote(quote)

    with pytest.raises(
        DomainConflict,
        match="Negotiation requires a verified competing quote",
    ):
        VoiceTools(repository, repository).get_verified_competing_quote(
            confirmed_record.job_spec.job_id,
            fixtures.load_vendors()[2].vendor_id,
            confirmed_record.job_spec.version,
        )


@pytest.mark.parametrize(
    "case",
    [
        "same_target_vendor",
        "partially_verified",
        "empty_evidence",
        "empty_verified_data",
        "manually_fabricated",
        "wrong_job_id",
        "wrong_job_spec_version",
    ],
)
def test_tools_reject_every_ineligible_leverage_case(
    case,
    monkeypatch,
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    vendors = fixtures.load_vendors()
    candidate = fixtures.load_initial_quotes()[0].model_copy(
        update={"job_id": confirmed_record.job_spec.job_id},
        deep=True,
    )
    target_vendor_id = vendors[2].vendor_id

    if case == "same_target_vendor":
        target_vendor_id = candidate.vendor.vendor_id
    elif case == "partially_verified":
        candidate = candidate.model_copy(
            update={"verification_status": VerificationStatus.PARTIALLY_VERIFIED},
            deep=True,
        )
    elif case == "empty_evidence":
        candidate = candidate.model_copy(
            update={"transcript_evidence": []},
            deep=True,
        )
    elif case == "empty_verified_data":
        candidate = candidate.model_copy(update={"verified_data": {}}, deep=True)
    elif case == "manually_fabricated":
        candidate = candidate.model_copy(update={"manually_fabricated": True}, deep=True)
    elif case == "wrong_job_id":
        candidate = candidate.model_copy(update={"job_id": uuid4()}, deep=True)
    else:
        # model_copy deliberately does not revalidate Literal["1.0"], which lets
        # this regression test exercise the repository's defensive predicate.
        candidate = candidate.model_copy(
            update={"job_spec_version": "0.9"},
            deep=True,
        )

    if case == "wrong_job_id":
        other_job = confirmed_record.model_copy(
            update={
                "job_spec": confirmed_record.job_spec.model_copy(
                    update={"job_id": candidate.job_id},
                    deep=True,
                )
            },
            deep=True,
        )
        repository.create(other_job)
        repository.save_quote(candidate)
    elif case in {"empty_evidence", "manually_fabricated", "wrong_job_spec_version"}:
        monkeypatch.setattr(repository, "list_quotes", lambda _job_id: [candidate])
    else:
        repository.save_quote(candidate)

    assert (
        repository.get_verified_competing_quote(
            confirmed_record.job_spec.job_id,
            target_vendor_id,
            confirmed_record.job_spec.version,
        )
        is None
    )
    with pytest.raises(
        DomainConflict,
        match="Negotiation requires a verified competing quote",
    ):
        VoiceTools(repository, repository).get_verified_competing_quote(
            confirmed_record.job_spec.job_id,
            target_vendor_id,
            confirmed_record.job_spec.version,
        )
