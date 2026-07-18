"""Contract-level validation tests."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from services.api.app.contracts import (
    CallOutcome,
    CallOutcomeType,
    JobSpecV1,
    MovingServices,
    QuoteV1,
)


def test_job_spec_accepts_nullable_future_vera_ids(job_spec_payload):
    model = JobSpecV1.model_validate(job_spec_payload)
    assert model.source_context.vera_user_id is None
    assert model.source_context.vera_property_id is None
    assert model.bedroom_count == 2


def test_job_spec_requires_inventory(job_spec_payload):
    payload = deepcopy(job_spec_payload)
    payload["inventory"] = []
    with pytest.raises(ValidationError, match="at least 1 item"):
        JobSpecV1.model_validate(payload)


def test_confirmation_fields_must_be_set_together(job_spec_payload):
    payload = deepcopy(job_spec_payload)
    payload["confirmed"] = True
    with pytest.raises(ValidationError, match="confirmed and confirmed_at"):
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
