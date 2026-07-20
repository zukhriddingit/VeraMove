"""Bounded provider-shape parsing for ElevenLabs events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from services.api.app.core.errors import WebhookPayloadError
from services.api.app.integrations.elevenlabs.models import (
    VerifiedCallInitiationFailure,
    VerifiedPostCallTranscription,
)
from services.api.app.integrations.elevenlabs.webhook import ElevenLabsWebhookProcessor
from services.api.tests.test_webhooks import WEBHOOK_SECRET, WEBHOOK_UNIX_TIME, sign

NOW = datetime.fromtimestamp(WEBHOOK_UNIX_TIME, UTC)
JOB_ID = "11111111-1111-4111-8111-111111111111"
CALL_ID = "22222222-2222-4222-8222-222222222222"


def processor() -> ElevenLabsWebhookProcessor:
    return ElevenLabsWebhookProcessor(
        secret=WEBHOOK_SECRET,
        clock=lambda: NOW,
    )


def post_call_payload(*, list_shape: bool = False) -> dict[str, object]:
    collection_map = {
        "outcome_type": {
            "data_collection_id": "outcome_type",
            "value": "itemized_quote",
            "rationale": "Sensitive provider rationale is discarded.",
        },
        "headline_total": {
            "data_collection_id": "headline_total",
            "value": 2300.5,
        },
        "recording_consent": {
            "data_collection_id": "recording_consent",
            "value": True,
        },
        "unknown_provider_field": {
            "data_collection_id": "unknown_provider_field",
            "value": "discard",
        },
    }
    analysis: dict[str, object] = {
        "data_collection_results": collection_map,
        "transcript_summary": "Sensitive summary is discarded.",
    }
    if list_shape:
        analysis = {
            "data_collection_results": {},
            "data_collection_results_list": list(collection_map.values()),
        }
    return {
        "type": "post_call_transcription",
        "event_timestamp": WEBHOOK_UNIX_TIME,
        "data": {
            "agent_id": "agent_synthetic_outbound",
            "agent_name": "Synthetic Agent",
            "conversation_id": "conv_synthetic_123",
            "status": "done",
            "version_id": "agtvrsn_synthetic_1",
            "environment": "production",
            "has_audio": True,
            "metadata": {
                "phone_call": {
                    "external_number": "+12025550100",
                }
            },
            "conversation_initiation_client_data": {
                "dynamic_variables": {
                    "job_id": JOB_ID,
                    "call_id": CALL_ID,
                    "call_mode": "quote",
                    "vendor_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                    "job_spec_version": "1.0",
                    "agent_config_version": "2",
                    "job_spec_sha256": "a" * 64,
                    "system__caller_id": "+12025550100",
                }
            },
            "transcript": [
                {
                    "role": "agent",
                    "message": "This is an AI assistant and this call is recorded.",
                    "time_in_call_secs": 0,
                    "tool_calls": None,
                },
                {
                    "role": "user",
                    "message": "The all-in synthetic total is 2300 dollars.",
                    "time_in_call_secs": 8,
                },
                {
                    "role": "agent",
                    "message": None,
                    "time_in_call_secs": 9,
                    "tool_calls": [{"request_id": "discard"}],
                },
            ],
            "analysis": analysis,
        },
    }


@pytest.mark.parametrize("list_shape", [False, True])
def test_signed_post_call_normalizes_map_and_list_collection_shapes(
    list_shape: bool,
) -> None:
    payload = post_call_payload(list_shape=list_shape)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()

    event = processor().process_provider_event(
        body,
        sign(body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME),
    )

    assert isinstance(event, VerifiedPostCallTranscription)
    assert event.agent_id == "agent_synthetic_outbound"
    assert event.event_timestamp == NOW
    assert event.dynamic_variables.job_id == UUID(JOB_ID)
    assert event.dynamic_variables.call_id == UUID(CALL_ID)
    assert event.dynamic_variables.call_mode == "quote"
    assert event.collected_data == {
        "headline_total": 2300.5,
        "outcome_type": "itemized_quote",
        "recording_consent": True,
    }
    assert len(event.transcript_turns) == 3
    assert event.transcript_turns[-1].message is None
    serialized = event.model_dump_json()
    assert "+12025550100" not in serialized
    assert "Sensitive" not in serialized
    assert "unknown_provider_field" not in serialized
    assert "tool_calls" not in serialized


def test_signed_post_call_deduplicates_dual_collection_representations() -> None:
    payload = post_call_payload()
    data = payload["data"]
    assert isinstance(data, dict)
    analysis = data["analysis"]
    assert isinstance(analysis, dict)
    results = analysis["data_collection_results"]
    assert isinstance(results, dict)
    for index in range(20):
        identifier = f"unknown_provider_field_{index}"
        results[identifier] = {
            "data_collection_id": identifier,
            "value": f"discard-{index}",
        }
    analysis["data_collection_results_list"] = list(results.values())
    body = json.dumps(payload).encode()

    event = processor().process_provider_event(
        body,
        sign(body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME),
    )

    assert isinstance(event, VerifiedPostCallTranscription)
    assert event.collected_data == {
        "headline_total": 2300.5,
        "outcome_type": "itemized_quote",
        "recording_consent": True,
    }


def test_signed_post_call_rejects_more_than_40_unique_collection_identifiers() -> None:
    payload = post_call_payload()
    data = payload["data"]
    assert isinstance(data, dict)
    analysis = data["analysis"]
    assert isinstance(analysis, dict)
    results = analysis["data_collection_results"]
    assert isinstance(results, dict)
    for index in range(37):
        identifier = f"unknown_provider_field_{index}"
        results[identifier] = {
            "data_collection_id": identifier,
            "value": f"discard-{index}",
        }
    body = json.dumps(payload).encode()

    with pytest.raises(WebhookPayloadError, match="too many items"):
        processor().process_provider_event(
            body,
            sign(body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME),
        )


def test_duplicate_collection_identifier_with_conflicting_value_is_rejected() -> None:
    payload = post_call_payload(list_shape=True)
    data = payload["data"]
    assert isinstance(data, dict)
    analysis = data["analysis"]
    assert isinstance(analysis, dict)
    entries = analysis["data_collection_results_list"]
    assert isinstance(entries, list)
    entries.append({"data_collection_id": "headline_total", "value": 999})
    body = json.dumps(payload).encode()

    with pytest.raises(WebhookPayloadError, match="duplicate"):
        processor().process_provider_event(
            body,
            sign(body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME),
        )


def test_missing_collection_value_remains_none() -> None:
    payload = post_call_payload()
    data = payload["data"]
    assert isinstance(data, dict)
    analysis = data["analysis"]
    assert isinstance(analysis, dict)
    results = analysis["data_collection_results"]
    assert isinstance(results, dict)
    results["deposit"] = {"data_collection_id": "deposit", "value": None}
    body = json.dumps(payload).encode()

    event = processor().process_provider_event(
        body,
        sign(body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME),
    )

    assert isinstance(event, VerifiedPostCallTranscription)
    assert event.collected_data["deposit"] is None


@pytest.mark.parametrize("reason", ["busy", "no-answer", "unknown"])
def test_signed_call_initiation_failure_discards_provider_metadata(reason: str) -> None:
    payload = {
        "type": "call_initiation_failure",
        "event_timestamp": WEBHOOK_UNIX_TIME,
        "data": {
            "agent_id": "agent_synthetic_outbound",
            "conversation_id": "conv_failed_123",
            "failure_reason": reason,
            "metadata": {
                "type": "twilio",
                "body": {
                    "Called": "+12025550100",
                    "CallSid": "CA_sensitive_provider_value",
                },
            },
        },
    }
    body = json.dumps(payload).encode()

    event = processor().process_provider_event(
        body,
        sign(body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME),
    )

    assert isinstance(event, VerifiedCallInitiationFailure)
    assert event.failure_reason == reason
    serialized = event.model_dump_json()
    assert "+12025550100" not in serialized
    assert "CA_sensitive" not in serialized


def test_provider_event_rejects_oversized_body_before_json_parsing() -> None:
    body = b"{" + b" " * (2_000_001) + b"}"

    with pytest.raises(WebhookPayloadError, match="too large"):
        processor().process_provider_event(
            body,
            sign(body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME),
        )
