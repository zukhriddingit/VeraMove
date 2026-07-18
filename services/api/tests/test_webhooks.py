"""HMAC, normalization, replay, and safe-event tests for voice webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from services.api.app.contracts import CallStatus, WebhookAck
from services.api.app.core.errors import (
    ResourceNotFound,
    WebhookAuthenticationError,
    WebhookPayloadError,
)
from services.api.app.integrations.elevenlabs.mock import MockVoiceProvider
from services.api.app.integrations.elevenlabs.webhook import (
    ElevenLabsWebhookProcessor,
)
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.orchestration.mock_intelligence import MockIntelligenceProvider
from services.api.app.orchestration.service import VeraMoveService
from services.api.app.repositories.memory import InMemoryRepository

WEBHOOK_UNIX_TIME = 1_750_000_000
WEBHOOK_NOW = datetime.fromtimestamp(WEBHOOK_UNIX_TIME, UTC)
WEBHOOK_SECRET = "synthetic-secret"


def sign(body: bytes, secret: str, timestamp: int) -> str:
    signed = str(timestamp).encode() + b"." + body
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v0={digest}"


@pytest.fixture
def processor() -> ElevenLabsWebhookProcessor:
    return ElevenLabsWebhookProcessor(
        secret=WEBHOOK_SECRET,
        clock=lambda: WEBHOOK_NOW,
    )


@pytest.fixture
def service_with_webhook(fixtures, job_spec) -> VeraMoveService:
    repository = InMemoryRepository()
    service = VeraMoveService(
        jobs=repository,
        calls=repository,
        quotes=repository,
        voice=MockVoiceProvider(fixtures),
        intelligence=MockIntelligenceProvider(
            fixtures,
            MockNegotiationGateway(fixtures),
        ),
        discovery=MockVendorDiscoveryGateway(fixtures),
        webhooks=ElevenLabsWebhookProcessor(
            secret=WEBHOOK_SECRET,
            clock=lambda: WEBHOOK_NOW,
        ),
        fixtures=fixtures,
        clock=lambda: WEBHOOK_NOW,
    )
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)
    service.start_calls(job_spec.job_id)
    return service


@pytest.fixture
def webhook_body(service_with_webhook, job_spec) -> bytes:
    attempt = service_with_webhook.list_call_attempts(job_spec.job_id)[0]
    assert attempt.reference is not None
    return json.dumps(
        {
            "type": "post_call_transcription",
            "event_timestamp": WEBHOOK_UNIX_TIME,
            "data": {
                "agent_id": "synthetic-agent",
                "conversation_id": attempt.reference.conversation_id,
                "status": "done",
                "transcript": [
                    {
                        "role": "agent",
                        "message": "Synthetic transcript must be discarded.",
                    }
                ],
                "analysis": {"summary": "Synthetic sensitive field."},
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def test_processor_rejects_invalid_and_stale_signatures(processor, webhook_body):
    with pytest.raises(WebhookAuthenticationError, match="signature"):
        processor.process(webhook_body, f"t={WEBHOOK_UNIX_TIME},v0=bad")

    stale = sign(webhook_body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME - 1_000)
    with pytest.raises(WebhookAuthenticationError, match="timestamp"):
        processor.process(webhook_body, stale)


@pytest.mark.parametrize(
    "signature",
    [None, "", "v0=abc", "t=not-an-int,v0=abc", "unexpected"],
)
def test_processor_rejects_missing_or_malformed_signatures(
    processor,
    webhook_body,
    signature,
):
    with pytest.raises(WebhookAuthenticationError):
        processor.process(webhook_body, signature)


def test_processor_authenticates_before_json_parsing(processor):
    with pytest.raises(WebhookAuthenticationError, match="signature"):
        processor.process(b"not-json", f"t={WEBHOOK_UNIX_TIME},v0=bad")


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"null", b'"text"'])
def test_processor_rejects_malformed_or_non_object_payloads(processor, body):
    signature = sign(body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME)
    with pytest.raises(WebhookPayloadError):
        processor.process(body, signature)


def test_processor_normalizes_only_safe_allowlisted_fields(processor, webhook_body):
    event = processor.process(
        webhook_body,
        sign(webhook_body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME),
    )

    assert event.event_type == "post_call_transcription"
    assert event.event_timestamp == WEBHOOK_NOW
    assert event.call_status is CallStatus.COMPLETED
    assert event.provider_status == "done"
    assert "transcript" not in event.model_fields_set
    assert "analysis" not in event.model_fields_set
    serialized = event.model_dump_json()
    assert "Synthetic transcript" not in serialized
    assert "Synthetic sensitive field" not in serialized


@pytest.mark.parametrize(
    ("provider_status", "call_status"),
    [
        ("done", CallStatus.COMPLETED),
        ("failed", CallStatus.FAILED),
        ("processing", None),
    ],
)
def test_processor_maps_only_known_provider_statuses(
    processor,
    provider_status,
    call_status,
):
    body = json.dumps(
        {
            "type": "post_call_transcription",
            "event_timestamp": WEBHOOK_UNIX_TIME,
            "data": {
                "conversation_id": "synthetic-conversation",
                "status": provider_status,
            },
        }
    ).encode()

    event = processor.process(
        body,
        sign(body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME),
    )

    assert event.call_status is call_status


def test_legacy_synthetic_event_keeps_explicit_key_and_header_timestamp(processor):
    body = json.dumps(
        {
            "idempotency_key": "synthetic-webhook-1",
            "event_type": "synthetic.call.completed",
            "payload": {"synthetic": True, "transcript": "discard me"},
        }
    ).encode()

    event = processor.process(
        body,
        sign(body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME),
    )

    assert event.idempotency_key == "synthetic-webhook-1"
    assert event.event_timestamp == WEBHOOK_NOW
    assert "payload" not in event.model_dump_json()


def test_webhook_replay_creates_one_safe_event(
    service_with_webhook,
    webhook_body,
    job_spec,
):
    signature = sign(webhook_body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME)

    first = service_with_webhook.handle_elevenlabs_webhook(webhook_body, signature)
    second = service_with_webhook.handle_elevenlabs_webhook(webhook_body, signature)

    assert first == WebhookAck(accepted=True, duplicate=False)
    assert second == WebhookAck(accepted=False, duplicate=True)
    events = service_with_webhook.get_events(job_spec.job_id)
    assert len(events) == 1
    assert events[0].event_type == "post_call_transcription"
    assert events[0].metadata == {"provider_status": "done"}
    matched_attempt = next(
        attempt
        for attempt in service_with_webhook.list_call_attempts(job_spec.job_id)
        if attempt.call_id == events[0].call_id
    )
    assert matched_attempt.status is CallStatus.COMPLETED
    assert matched_attempt.completed_at == WEBHOOK_NOW
    serialized = json.dumps([event.model_dump(mode="json") for event in events])
    assert "Synthetic transcript" not in serialized
    assert "Synthetic sensitive field" not in serialized


def test_signed_unmatched_conversation_is_reserved_without_event(
    service_with_webhook,
    job_spec,
):
    body = json.dumps(
        {
            "type": "post_call_transcription",
            "event_timestamp": WEBHOOK_UNIX_TIME,
            "data": {
                "conversation_id": "synthetic-unmatched-conversation",
                "status": "done",
            },
        }
    ).encode()
    signature = sign(body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME)

    first = service_with_webhook.handle_elevenlabs_webhook(body, signature)
    second = service_with_webhook.handle_elevenlabs_webhook(body, signature)

    assert first == WebhookAck(accepted=True, duplicate=False)
    assert second == WebhookAck(accepted=False, duplicate=True)
    assert service_with_webhook.get_events(job_spec.job_id) == []


def test_get_events_requires_existing_job(service_with_webhook):
    with pytest.raises(ResourceNotFound):
        service_with_webhook.get_events(uuid4())


def test_missing_live_webhook_secret_fails_on_processing_not_construction(
    webhook_body,
):
    processor = ElevenLabsWebhookProcessor(
        secret=None,
        clock=lambda: WEBHOOK_NOW,
    )

    with pytest.raises(WebhookAuthenticationError, match="not configured"):
        processor.process(
            webhook_body,
            sign(webhook_body, WEBHOOK_SECRET, WEBHOOK_UNIX_TIME),
        )
