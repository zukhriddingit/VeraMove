"""Contract-level validation tests."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from services.api.app.contracts import (
    AmountStatus,
    CallOutcome,
    CallOutcomeType,
    FeeCategory,
    FeeLineItem,
    JobSpecV1,
    MovingServices,
    QuoteV1,
)


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
