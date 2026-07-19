"""Canonical outbound materialization from authenticated provider analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import HttpUrl

from services.api.app.contracts import (
    CallOutcomeType,
    CallStatus,
    FeeCategory,
    VerificationStatus,
)
from services.api.app.core.errors import DomainConflict
from services.api.app.integrations.elevenlabs.models import (
    ElevenLabsDynamicVariables,
    ElevenLabsTranscriptTurn,
    VerifiedPostCallTranscription,
)
from services.api.app.intelligence.quotes import QuoteVerifier
from services.api.app.orchestration.models import (
    CallAttempt,
    CallKind,
    VoiceCallReference,
)
from services.api.app.orchestration.outbound_materializer import (
    materialize_outbound_event,
)

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
RECORDING_URL = HttpUrl("https://api.veramove.example/api/calls/synthetic/recording")


def make_attempt(job_spec, vendor) -> CallAttempt:
    return CallAttempt(
        call_id=uuid4(),
        job_id=job_spec.job_id,
        kind=CallKind.QUOTE,
        vendor=vendor,
        job_spec_snapshot=job_spec,
        destination_slot=0,
        expected_agent_id="agent_synthetic_outbound",
        agent_config_version="2026-07-19.1",
        status=CallStatus.IN_PROGRESS,
        started_at=NOW,
        reference=VoiceCallReference(
            conversation_id="conv_synthetic_materialization",
            provider_call_id="CA_synthetic_materialization",
        ),
    )


def make_event(attempt: CallAttempt, **updates) -> VerifiedPostCallTranscription:
    collected_data = {
        "recording_consent": True,
        "outcome_type": "itemized_quote",
        "headline_total": 120,
        "original_total": 120,
        "negotiated_total": 120,
        "deposit": 12,
        "binding_type": "binding",
        "availability_status": "available",
        "availability": "Available on the synthetic requested date.",
        "fee_items_json": json.dumps(
            [
                {
                    "category": "base_service",
                    "description": "Synthetic base service fee.",
                    "amount": "100.00",
                    "mandatory": True,
                },
                {
                    "category": "stairs",
                    "description": "Synthetic stairs fee.",
                    "amount": "20.00",
                    "mandatory": True,
                },
            ]
        ),
        "addressed_fee_categories_json": json.dumps(["base_service", "stairs"]),
        "concessions_json": "[]",
    }
    collected_data.update(updates.pop("collected_data", {}))
    values = {
        "idempotency_key": "synthetic-event-key",
        "event_timestamp": NOW.replace(minute=5),
        "agent_id": attempt.expected_agent_id,
        "conversation_id": attempt.reference.conversation_id,
        "provider_status": "done",
        "call_status": CallStatus.COMPLETED,
        "version_id": "agtvrsn_synthetic_1",
        "has_audio": True,
        "dynamic_variables": ElevenLabsDynamicVariables(
            job_id=attempt.job_id,
            call_id=attempt.call_id,
            vendor_id=attempt.vendor.vendor_id,
            call_mode=attempt.call_mode,
            job_spec_version=attempt.job_spec_version,
            agent_config_version=attempt.agent_config_version,
            job_spec_sha256=attempt.job_spec_sha256,
        ),
        "collected_data": collected_data,
        "transcript_turns": (
            ElevenLabsTranscriptTurn(
                role="user",
                message="The base service fee is $100.00.",
                time_in_call_secs=Decimal("5"),
            ),
            ElevenLabsTranscriptTurn(
                role="user",
                message="The stairs fee is $20.00.",
                time_in_call_secs=Decimal("10"),
            ),
            ElevenLabsTranscriptTurn(
                role="user",
                message="The all-in total is $120.00.",
                time_in_call_secs=Decimal("15"),
            ),
            ElevenLabsTranscriptTurn(
                role="user",
                message="This is a binding quote.",
                time_in_call_secs=Decimal("20"),
            ),
            ElevenLabsTranscriptTurn(
                role="user",
                message="We are available on the synthetic requested date.",
                time_in_call_secs=Decimal("25"),
            ),
        ),
    }
    values.update(updates)
    return VerifiedPostCallTranscription(**values)


def materialize(event, attempt):
    return materialize_outbound_event(
        event=event,
        attempt=attempt,
        recording_url=RECORDING_URL,
        verifier=QuoteVerifier(),
        required_fee_categories={FeeCategory.BASE_SERVICE, FeeCategory.STAIRS},
    )


def test_materializes_evidence_backed_itemized_quote(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])

    result = materialize(make_event(attempt), attempt)

    assert result.outcome.type is CallOutcomeType.ITEMIZED_QUOTE
    assert result.recording_url == RECORDING_URL
    assert result.provider_version_id == "agtvrsn_synthetic_1"
    quote = result.outcome.quote
    assert quote is not None
    assert quote.job_id == attempt.job_id
    assert quote.vendor == attempt.vendor
    assert quote.comparable_total == Decimal("120.00")
    assert quote.verification_status is VerificationStatus.VERIFIED
    assert len(quote.transcript_evidence) == 5
    assert all(item.recording_url == RECORDING_URL for item in quote.transcript_evidence)
    assert all(item.evidence_ids for item in quote.fee_line_items)


def test_unsupported_material_fee_remains_partial(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    event = make_event(
        attempt,
        transcript_turns=(
            ElevenLabsTranscriptTurn(
                role="user",
                message="The base service fee is $100 and total is $120, binding and available.",
                time_in_call_secs=Decimal("5"),
            ),
        ),
    )

    result = materialize(event, attempt)

    quote = result.outcome.quote
    assert quote is not None
    assert quote.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert "fee:stairs" in quote.verified_data["missing_evidence_claims"]


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("agent_id", "wrong-agent", "agent"),
        ("conversation_id", "wrong-conversation", "conversation"),
        ("job_spec_sha256", "0" * 64, "snapshot"),
        ("agent_config_version", "wrong-version", "agent_config"),
    ],
)
def test_rejects_repository_correlation_mismatches(
    field,
    value,
    expected,
    job_spec,
    fixtures,
):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    event = make_event(attempt)
    if field in {"job_spec_sha256", "agent_config_version"}:
        event = event.model_copy(
            update={"dynamic_variables": event.dynamic_variables.model_copy(update={field: value})},
            deep=True,
        )
    else:
        event = event.model_copy(update={field: value}, deep=True)

    with pytest.raises(DomainConflict, match=expected):
        materialize(event, attempt)


def test_materializes_failed_outcome_without_fake_recording(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    event = make_event(attempt).model_copy(
        update={
            "has_audio": False,
            "collected_data": {
                "outcome_type": "failed",
                "outcome_reason": "The synthetic participant did not answer.",
                "recording_consent": False,
            },
            "transcript_turns": (),
        },
        deep=True,
    )

    result = materialize(event, attempt)

    assert result.outcome.type is CallOutcomeType.FAILED
    assert result.outcome.reason == "The synthetic participant did not answer."
    assert result.recording_url is None


def test_non_quote_never_exposes_saved_audio_without_recording_consent(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    event = make_event(attempt).model_copy(
        update={
            "has_audio": True,
            "collected_data": {
                "outcome_type": "documented_decline",
                "outcome_reason": "The synthetic participant declined recording.",
                "recording_consent": False,
            },
            "transcript_turns": (),
        },
        deep=True,
    )

    result = materialize(event, attempt)

    assert result.outcome.type is CallOutcomeType.DOCUMENTED_DECLINE
    assert result.recording_url is None


def test_rejects_mixed_outcome_details(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    event = make_event(
        attempt,
        collected_data={"callback_at": "2026-07-20T12:00:00Z"},
    )

    with pytest.raises(DomainConflict, match="mixed details"):
        materialize(event, attempt)
