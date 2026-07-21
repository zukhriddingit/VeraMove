"""Contract-level validation tests."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from services.api.app.api.models import CreateIntakeSessionRequest
from services.api.app.contracts import (
    AmountStatus,
    CallOutcome,
    CallOutcomeType,
    CallRecord,
    CallStatus,
    FeeCategory,
    FeeLineItem,
    JobSpecV1,
    MovingServices,
    QuoteV1,
)
from services.api.app.orchestration.intake_sessions import IntakeDataMode


def test_job_spec_accepts_nullable_future_vera_ids(job_spec_payload):
    model = JobSpecV1.model_validate(job_spec_payload)
    assert model.source_context.vera_user_id is None
    assert model.source_context.vera_property_id is None
    assert model.bedroom_count == 2


def test_unconfirmed_job_spec_preserves_missing_inventory(job_spec_payload):
    payload = deepcopy(job_spec_payload)
    payload["inventory"] = []
    model = JobSpecV1.model_validate(payload)
    assert "inventory" in model.missing_required_fields()


def test_confirmed_job_spec_requires_inventory_and_locked_version(job_spec_payload):
    payload = deepcopy(job_spec_payload)
    payload.update(
        {
            "inventory": [],
            "confirmed": True,
            "confirmed_at": "2026-07-18T15:00:00Z",
            "locked_version": "1.0",
        }
    )
    with pytest.raises(ValidationError, match="missing required fields: inventory"):
        JobSpecV1.model_validate(payload)


def test_confirmation_fields_must_be_set_together(job_spec_payload):
    payload = deepcopy(job_spec_payload)
    payload["confirmed"] = True
    with pytest.raises(ValidationError, match="confirmed and confirmed_at"):
        JobSpecV1.model_validate(payload)


def test_confirmation_requires_current_version_lock(job_spec_payload):
    payload = deepcopy(job_spec_payload)
    payload["confirmed"] = True
    payload["confirmed_at"] = "2026-07-18T15:00:00Z"
    with pytest.raises(ValidationError, match="lock its current version"):
        JobSpecV1.model_validate(payload)


def test_storage_days_match_request():
    with pytest.raises(ValidationError, match="storage_days is required"):
        MovingServices(storage=True)


def test_create_intake_session_defaults_to_supervised_role_play():
    request = CreateIntakeSessionRequest()

    assert request.data_mode is IntakeDataMode.SUPERVISED_ROLE_PLAY


def test_create_intake_session_accepts_real_redacted_mode():
    request = CreateIntakeSessionRequest(data_mode="real_redacted")

    assert request.data_mode is IntakeDataMode.REAL_REDACTED


def test_call_outcome_enum_is_closed():
    assert {value.value for value in CallOutcomeType} == {
        "itemized_quote",
        "callback_commitment",
        "documented_decline",
        "failed",
    }


def test_itemized_outcome_requires_quote():
    with pytest.raises(ValidationError, match="require quote"):
        CallOutcome(type=CallOutcomeType.ITEMIZED_QUOTE)


@pytest.mark.parametrize(
    ("outcome_type", "extra_details"),
    [
        (
            CallOutcomeType.ITEMIZED_QUOTE,
            {"reason": "Mixed outcome details are ambiguous."},
        ),
        (
            CallOutcomeType.CALLBACK_COMMITMENT,
            {"quote": "quote"},
        ),
        (
            CallOutcomeType.DOCUMENTED_DECLINE,
            {"callback_at": datetime(2026, 7, 20, 17, 0, tzinfo=UTC)},
        ),
        (
            CallOutcomeType.FAILED,
            {"quote": "quote"},
        ),
    ],
)
def test_call_outcomes_reject_details_from_another_type(
    outcome_type,
    extra_details,
    fixtures,
):
    quote = fixtures.load_initial_quotes()[0]
    valid_details = {
        CallOutcomeType.ITEMIZED_QUOTE: {"quote": quote},
        CallOutcomeType.CALLBACK_COMMITMENT: {
            "callback_at": datetime(2026, 7, 20, 16, 0, tzinfo=UTC),
        },
        CallOutcomeType.DOCUMENTED_DECLINE: {"reason": "Vendor declined."},
        CallOutcomeType.FAILED: {"reason": "Call did not connect."},
    }[outcome_type]
    normalized_extras = {
        key: quote if value == "quote" else value
        for key, value in extra_details.items()
    }

    with pytest.raises(ValidationError, match="only permits"):
        CallOutcome(
            type=outcome_type,
            **valid_details,
            **normalized_extras,
        )


def test_each_call_outcome_accepts_only_its_supported_shape(fixtures):
    quote = fixtures.load_initial_quotes()[0]
    callback_at = datetime(2026, 7, 20, 16, 0, tzinfo=UTC)

    assert CallOutcome(type=CallOutcomeType.ITEMIZED_QUOTE, quote=quote).quote == quote
    assert (
        CallOutcome(
            type=CallOutcomeType.CALLBACK_COMMITMENT,
            callback_at=callback_at,
        ).callback_at
        == callback_at
    )
    assert (
        CallOutcome(
            type=CallOutcomeType.DOCUMENTED_DECLINE,
            reason="Vendor declined.",
        ).reason
        == "Vendor declined."
    )
    assert (
        CallOutcome(
            type=CallOutcomeType.FAILED,
            reason="Call did not connect.",
        ).reason
        == "Call did not connect."
    )


def _call_record_payload(fixtures, **updates):
    quote = fixtures.load_initial_quotes()[0]
    evidence = quote.transcript_evidence[0]
    payload = {
        "call_id": evidence.call_id,
        "job_id": quote.job_id,
        "vendor": quote.vendor,
        "status": CallStatus.COMPLETED,
        "started_at": datetime(2026, 7, 18, 16, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 7, 18, 17, 0, tzinfo=UTC),
        "outcome": CallOutcome(type=CallOutcomeType.ITEMIZED_QUOTE, quote=quote),
        "recording_url": quote.recording_url,
    }
    payload.update(updates)
    return payload


def test_completed_call_record_requires_completion_time(fixtures):
    with pytest.raises(ValidationError, match="terminal calls require completed_at"):
        CallRecord(**_call_record_payload(fixtures, completed_at=None))


def test_call_record_rejects_non_terminal_status_with_terminal_outcome(fixtures):
    with pytest.raises(ValidationError, match="canonical call records require terminal status"):
        CallRecord(**_call_record_payload(fixtures, status=CallStatus.IN_PROGRESS))


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (
            CallStatus.COMPLETED,
            CallOutcome(
                type=CallOutcomeType.FAILED,
                reason="The synthetic call did not connect.",
            ),
        ),
        (
            CallStatus.FAILED,
            CallOutcome(
                type=CallOutcomeType.DOCUMENTED_DECLINE,
                reason="The vendor declined.",
            ),
        ),
    ],
)
def test_call_record_status_matches_outcome(status, outcome, fixtures):
    with pytest.raises(ValidationError, match="outcomes require status"):
        CallRecord(
            **_call_record_payload(
                fixtures,
                status=status,
                outcome=outcome,
                recording_url=None,
            )
        )


def test_itemized_call_record_requires_recording_url(fixtures):
    with pytest.raises(ValidationError, match="itemized_quote calls require recording_url"):
        CallRecord(**_call_record_payload(fixtures, recording_url=None))


def test_failed_never_connected_call_may_omit_recording_url(fixtures):
    outcome = CallOutcome(
        type=CallOutcomeType.FAILED,
        reason="The synthetic call never connected.",
    )

    call = CallRecord(
        **_call_record_payload(
            fixtures,
            status=CallStatus.FAILED,
            outcome=outcome,
            recording_url=None,
        )
    )

    assert call.recording_url is None


def test_callback_commitment_requires_timezone_aware_timestamp():
    with pytest.raises(ValidationError, match="callback_at must include a timezone"):
        CallOutcome(
            type=CallOutcomeType.CALLBACK_COMMITMENT,
            callback_at=datetime(2026, 7, 20, 16, 0),
        )


def test_callback_must_follow_call_completion(fixtures):
    completed_at = datetime(2026, 7, 18, 17, 0, tzinfo=UTC)
    outcome = CallOutcome(
        type=CallOutcomeType.CALLBACK_COMMITMENT,
        callback_at=completed_at - timedelta(minutes=1),
    )

    with pytest.raises(ValidationError, match="callback_at must follow completed_at"):
        CallRecord(
            **_call_record_payload(
                fixtures,
                outcome=outcome,
                recording_url=None,
            )
        )


@pytest.mark.parametrize(
    "mismatch",
    [
        "job",
        "vendor",
        "evidence_call",
        "quote_recording",
        "evidence_recording",
    ],
)
def test_itemized_call_record_rejects_cross_identity_quote_data(mismatch, fixtures):
    quote = fixtures.load_initial_quotes()[0]
    other_quote = fixtures.load_initial_quotes()[1]
    call_updates = {}

    if mismatch == "job":
        call_updates["job_id"] = uuid4()
    elif mismatch == "vendor":
        call_updates["vendor"] = other_quote.vendor
    elif mismatch == "evidence_call":
        quote = quote.model_copy(
            update={
                "transcript_evidence": [
                    quote.transcript_evidence[0].model_copy(
                        update={"call_id": uuid4()},
                        deep=True,
                    )
                ]
            },
            deep=True,
        )
    elif mismatch == "quote_recording":
        quote = quote.model_copy(
            update={"recording_url": "https://recordings.example.com/other-call"},
            deep=True,
        )
    else:
        quote = quote.model_copy(
            update={
                "transcript_evidence": [
                    quote.transcript_evidence[0].model_copy(
                        update={
                            "recording_url": (
                                "https://recordings.example.com/other-evidence"
                            )
                        },
                        deep=True,
                    )
                ]
            },
            deep=True,
        )

    with pytest.raises(ValidationError, match="itemized quote identity"):
        CallRecord(
            **_call_record_payload(
                fixtures,
                outcome=CallOutcome(
                    type=CallOutcomeType.ITEMIZED_QUOTE,
                    quote=quote,
                ),
                **call_updates,
            )
        )


def test_quote_rejects_non_usd_currency(fixtures):
    payload = fixtures.load_initial_quotes()[0].model_dump(mode="json")
    payload["currency"] = "EUR"
    with pytest.raises(ValidationError):
        QuoteV1.model_validate(payload)


def test_quote_serializes_decimal_totals(fixtures):
    quote = fixtures.load_initial_quotes()[0]
    payload = quote.model_dump(mode="json")
    assert payload["original_total"] == "2400.00"
    assert payload["negotiated_total"] == "2400.00"


def test_fee_contract_distinguishes_unknown_from_zero():
    zero = FeeLineItem(
        category=FeeCategory.FUEL,
        description="Vendor explicitly stated no fuel fee.",
        amount="0.00",
    )
    unknown = FeeLineItem(
        category=FeeCategory.FUEL,
        description="Fuel fee mentioned without an amount.",
        amount_status=AmountStatus.UNKNOWN,
    )
    assert zero.amount == 0
    assert zero.amount_status is AmountStatus.KNOWN
    assert unknown.amount is None


def test_unknown_fee_rejects_numeric_amount():
    with pytest.raises(ValidationError, match="must not contain an amount"):
        FeeLineItem(
            category=FeeCategory.FUEL,
            description="Contradictory unknown fee.",
            amount="1.00",
            amount_status=AmountStatus.UNKNOWN,
        )
