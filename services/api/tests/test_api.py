"""HTTP contract and mock-flow tests."""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from services.api.app.api.dependencies import (
    get_browser_voice_token_issuer,
    get_live_voice_operator_service,
    get_service,
)
from services.api.app.contracts import (
    DataClassification,
    IntakeSource,
    JobRecord,
    JobState,
    WebhookAck,
)
from services.api.app.core.config import LiveVoiceConfig, Settings, SupabaseConfig
from services.api.app.core.errors import ProviderRequestError
from services.api.app.main import create_app
from services.api.app.orchestration.intake_sessions import IntakeSessionService
from services.api.app.orchestration.live_voice_operator import RecordingProxyPayload

WEBHOOK_SECRET = "synthetic-webhook-secret"
WEBHOOK_TIMESTAMP = int(datetime(2026, 7, 18, 16, 0, tzinfo=UTC).timestamp())


def sign_webhook(body: bytes) -> str:
    signed = str(WEBHOOK_TIMESTAMP).encode() + b"." + body
    digest = hmac.new(WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={WEBHOOK_TIMESTAMP},v0={digest}"


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "mock",
        "service": "veramove-api",
    }


def test_health_reflects_live_runtime_mode_without_dialing(monkeypatch):
    monkeypatch.setenv("APP_MODE", "live")
    live_app = create_app()

    with TestClient(live_app) as test_client:
        response = test_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "live",
        "service": "veramove-api",
    }


def test_configured_public_origin_passes_cors_preflight(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://veramove-demo.example")
    configured_app = create_app()

    with TestClient(configured_app) as test_client:
        response = test_client.options(
            "/health",
            headers={
                "Origin": "https://veramove-demo.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ("https://veramove-demo.example")


def test_recording_route_streams_validated_audio_with_no_store():
    call_id = uuid4()
    job_id = uuid4()

    class Operator:
        def fetch_recording(self, received_call_id, received_job_id, signature):
            assert (received_call_id, received_job_id, signature) == (
                call_id,
                job_id,
                "a" * 64,
            )
            return RecordingProxyPayload(
                content=b"synthetic-audio",
                media_type="audio/mpeg",
                content_length=len(b"synthetic-audio"),
            )

    application = create_app(Settings())
    application.dependency_overrides[get_live_voice_operator_service] = Operator
    with TestClient(application) as test_client:
        response = test_client.get(
            f"/api/calls/{call_id}/recording",
            params={"job_id": str(job_id), "signature": "a" * 64},
        )

    assert response.status_code == 200
    assert response.content == b"synthetic-audio"
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "no-store"


def test_repair_route_forwards_authenticated_typed_input_to_canonical_service():
    call_id = uuid4()
    prepared = object()

    class Operator:
        def prepare_repair(self, received_call_id, supplied_secret):
            assert received_call_id == call_id
            assert supplied_secret == "synthetic-operator-secret"
            return prepared

    class Service:
        def handle_elevenlabs_repair(self, repair):
            assert repair is prepared
            return WebhookAck(accepted=True, duplicate=False)

    application = create_app(Settings())
    application.dependency_overrides[get_live_voice_operator_service] = Operator
    application.dependency_overrides[get_service] = Service
    with TestClient(application) as test_client:
        response = test_client.post(
            f"/api/calls/{call_id}/repair",
            headers={"x-veramove-operator-secret": "synthetic-operator-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"accepted": True, "duplicate": False}


def test_api_happy_path(client, job_spec_payload):
    created = client.post("/api/jobs", json=job_spec_payload)
    assert created.status_code == 201
    job_id = created.json()["job_spec"]["job_id"]

    fetched = client.get(f"/api/jobs/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["state"] == "intake_complete"

    confirmed = client.post(f"/api/jobs/{job_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["job_spec"]["confirmed"] is True

    calls = client.post(f"/api/jobs/{job_id}/calls")
    assert calls.status_code == 200
    assert len(calls.json()["calls"]) == 3
    assert len(calls.json()["quotes"]) == 3

    negotiated = client.post(f"/api/jobs/{job_id}/negotiate")
    assert negotiated.status_code == 200
    assert negotiated.json()["state"] == "completed"
    assert len(negotiated.json()["quotes"]) == 4

    report = client.get(f"/api/jobs/{job_id}/report")
    assert report.status_code == 200
    assert report.json()["rankings"][0]["evidence_ids"]
    assert len(report.json()["transcript_evidence"]) == 3
    assert all(item["recording_url"] for item in report.json()["transcript_evidence"])


def test_unconfirmed_job_spec_update_round_trips_through_api(client, job_spec_payload):
    created = client.post("/api/jobs", json=job_spec_payload)
    assert created.status_code == 201
    job_id = created.json()["job_spec"]["job_id"]
    replacement = created.json()["job_spec"]
    replacement["bedroom_count"] = 3

    updated = client.put(f"/api/jobs/{job_id}", json=replacement)

    assert updated.status_code == 200
    assert updated.json()["state"] == "intake_complete"
    assert updated.json()["job_spec"]["bedroom_count"] == 3
    assert client.get(f"/api/jobs/{job_id}").json() == updated.json()


def test_job_spec_update_rejects_mismatched_or_confirmed_identity(client, job_spec_payload):
    created = client.post("/api/jobs", json=job_spec_payload)
    job_id = created.json()["job_spec"]["job_id"]
    mismatched = created.json()["job_spec"]
    mismatched["job_id"] = str(uuid4())

    mismatch_response = client.put(f"/api/jobs/{job_id}", json=mismatched)
    assert mismatch_response.status_code == 409
    assert mismatch_response.json()["error"]["code"] == "domain_conflict"

    confirmed = client.post(f"/api/jobs/{job_id}/confirm")
    assert confirmed.status_code == 200
    replacement = confirmed.json()["job_spec"]
    replacement.update(
        {
            "confirmed": False,
            "confirmed_at": None,
            "locked_version": None,
            "bedroom_count": 4,
        }
    )
    confirmed_response = client.put(f"/api/jobs/{job_id}", json=replacement)
    assert confirmed_response.status_code == 409
    assert confirmed_response.json()["error"]["code"] == "domain_conflict"


def test_complete_document_to_report_flow_is_idempotent(client):
    intake = client.post(
        "/api/intake/document",
        json={"document_text": "Synthetic inventory for the VeraMove demo."},
    )
    assert intake.status_code == 201
    job_id = intake.json()["job_spec"]["job_id"]

    first_confirm = client.post(f"/api/jobs/{job_id}/confirm")
    second_confirm = client.post(f"/api/jobs/{job_id}/confirm")
    assert first_confirm.status_code == 200
    assert first_confirm.json() == second_confirm.json()

    first_calls = client.post(f"/api/jobs/{job_id}/calls")
    second_calls = client.post(f"/api/jobs/{job_id}/calls")
    assert first_calls.status_code == 200
    assert first_calls.json() == second_calls.json()
    assert len(first_calls.json()["calls"]) == 3
    assert {item["outcome"]["type"] for item in first_calls.json()["calls"]} == {"itemized_quote"}
    assert {
        item["outcome"]["quote"]["job_spec_version"] for item in first_calls.json()["calls"]
    } == {"1.0"}

    completed = client.post(f"/api/jobs/{job_id}/negotiate")
    assert completed.status_code == 200
    assert completed.json()["state"] == "completed"
    assert len(completed.json()["quotes"]) == 4
    repeated = client.post(f"/api/jobs/{job_id}/negotiate")
    assert repeated.status_code == 200
    assert repeated.json() == completed.json()

    report = client.get(f"/api/jobs/{job_id}/report")
    assert report.status_code == 200
    assert report.json()["rankings"][0]["evidence_ids"]
    assert all(item["recording_url"] for item in report.json()["transcript_evidence"])


def test_illegal_api_transition_is_conflict(client, job_spec_payload):
    created = client.post("/api/jobs", json=job_spec_payload)
    job_id = created.json()["job_spec"]["job_id"]
    response = client.post(f"/api/jobs/{job_id}/calls")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state_transition"


def test_unknown_job_is_not_found(client):
    response = client.get(f"/api/jobs/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


def test_document_intake_and_events_routes(client):
    intake = client.post(
        "/api/intake/document",
        json={"document_text": "Synthetic two-bedroom move inventory."},
    )
    assert intake.status_code == 201
    job_id = intake.json()["job_spec"]["job_id"]
    assert intake.json()["job_spec"]["intake_source"] == "document"

    events = client.get(f"/api/jobs/{job_id}/events")
    assert events.status_code == 200
    assert events.json() == {"events": []}


def test_web_intake_session_is_created_without_an_incomplete_job(client):
    created = client.post("/api/intake/sessions")

    assert created.status_code == 201
    payload = created.json()
    assert payload == {
        "intake_session_id": payload["intake_session_id"],
        "job_id": payload["job_id"],
        "status": "pending",
        "conversation_id": None,
        "job_spec": None,
    }
    fetched = client.get(f"/api/intake/sessions/{payload['intake_session_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == payload
    assert client.get(f"/api/jobs/{payload['job_id']}").status_code == 404


def test_unknown_intake_session_and_conversation_are_not_found(client):
    assert client.get(f"/api/intake/sessions/{uuid4()}").status_code == 404
    response = client.get("/api/intake/conversations/unknown-synthetic-conversation")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


class StaticBrowserTokenIssuer:
    def __init__(self, token: str = "synthetic-ephemeral-token") -> None:
        self.token = token
        self.calls = 0

    def issue_token(self) -> str:
        self.calls += 1
        return self.token


def browser_voice_settings() -> Settings:
    return Settings(
        app_mode="live",
        live_voice=LiveVoiceConfig(
            api_key="synthetic-elevenlabs-key",
            intake_agent_id="synthetic-intake-agent",
            webhook_secret="w" * 32,
            agent_config_version="2026-07-19.browser-v1",
            live_calls_enabled=True,
        ),
        supabase=SupabaseConfig(
            enabled=True,
            url="https://synthetic-project.supabase.co",
            secret_key="synthetic-supabase-secret",
        ),
    )


def test_browser_voice_token_and_conversation_routes_are_correlated_and_no_store():
    application = create_app(Settings())
    application.state.settings = browser_voice_settings()
    issuer = StaticBrowserTokenIssuer()
    application.dependency_overrides[get_browser_voice_token_issuer] = lambda: issuer

    with TestClient(application) as test_client:
        session = test_client.post("/api/intake/sessions").json()
        issued = test_client.post(
            f"/api/intake/sessions/{session['intake_session_id']}/voice-token"
        )
        attached = test_client.post(
            f"/api/intake/sessions/{session['intake_session_id']}/conversation",
            json={"conversation_id": "conv_synthetic_browser"},
        )

    assert issued.status_code == 200
    assert issued.headers["cache-control"] == "no-store"
    assert issued.json() == {
        "conversation_token": "synthetic-ephemeral-token",
        "dynamic_variables": {
            "job_id": session["job_id"],
            "intake_session_id": session["intake_session_id"],
            "agent_config_version": "2026-07-19.browser-v1",
        },
    }
    assert "synthetic-elevenlabs-key" not in issued.text
    assert "synthetic-intake-agent" not in issued.text
    assert issuer.calls == 1
    assert attached.status_code == 200
    assert attached.json()["status"] == "in_progress"
    assert attached.json()["conversation_id"] == "conv_synthetic_browser"


def test_browser_voice_token_is_single_use_and_mock_mode_is_rejected():
    mock_application = create_app(Settings())
    with TestClient(mock_application) as test_client:
        session = test_client.post("/api/intake/sessions").json()
        rejected = test_client.post(
            f"/api/intake/sessions/{session['intake_session_id']}/voice-token"
        )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "provider_configuration_error"

    application = create_app(Settings())
    application.state.settings = browser_voice_settings()
    issuer = StaticBrowserTokenIssuer()
    application.dependency_overrides[get_browser_voice_token_issuer] = lambda: issuer
    with TestClient(application) as test_client:
        unknown = test_client.post(f"/api/intake/sessions/{uuid4()}/voice-token")
        session = test_client.post("/api/intake/sessions").json()
        path = f"/api/intake/sessions/{session['intake_session_id']}/voice-token"
        assert test_client.post(path).status_code == 200
        replay = test_client.post(path)
        attached_path = f"/api/intake/sessions/{session['intake_session_id']}/conversation"
        first_attach = test_client.post(
            attached_path,
            json={"conversation_id": "conv_synthetic_browser"},
        )
        same_attach = test_client.post(
            attached_path,
            json={"conversation_id": "conv_synthetic_browser"},
        )
        changed_attach = test_client.post(
            attached_path,
            json={"conversation_id": "conv_synthetic_other"},
        )

    assert unknown.status_code == 404
    assert replay.status_code == 409
    assert issuer.calls == 1
    assert first_attach.status_code == 200
    assert same_attach.status_code == 200
    assert changed_attach.status_code == 409


def test_provider_failure_marks_reserved_session_failed_without_returning_token():
    class FailingIssuer:
        def issue_token(self) -> str:
            raise ProviderRequestError("synthetic safe provider failure")

    application = create_app(Settings())
    application.state.settings = browser_voice_settings()
    application.dependency_overrides[get_browser_voice_token_issuer] = FailingIssuer
    with TestClient(application) as test_client:
        session = test_client.post("/api/intake/sessions").json()
        issued = test_client.post(
            f"/api/intake/sessions/{session['intake_session_id']}/voice-token"
        )
        stored = test_client.get(f"/api/intake/sessions/{session['intake_session_id']}")

    assert issued.status_code == 502
    assert stored.json()["status"] == "failed"
    assert "token" not in stored.text


def test_pre_call_secret_is_checked_before_malformed_body_is_read():
    settings = Settings(
        app_mode="mock",
        live_voice=LiveVoiceConfig(
            intake_agent_id="synthetic-intake-agent",
            precall_secret="p" * 32,
            agent_config_version="2026-07-19.1",
        ),
    )
    configured_app = create_app(settings)

    with TestClient(configured_app) as test_client:
        response = test_client.post(
            "/api/webhooks/elevenlabs/pre-call",
            content=b"not-json-and-must-not-be-parsed",
            headers={"x-veramove-precall-secret": "wrong"},
        )
        authenticated = test_client.post(
            "/api/webhooks/elevenlabs/pre-call",
            content=b"not-json-and-now-may-be-parsed",
            headers={"x-veramove-precall-secret": "p" * 32},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "webhook_authentication_error"
    assert authenticated.status_code == 400
    assert authenticated.json()["error"]["code"] == "webhook_payload_error"
    assert configured_app.state.repository._intake_sessions == {}


def test_pre_call_is_idempotent_redacted_and_returns_exact_dynamic_variables(job_spec):
    settings = Settings(
        app_mode="mock",
        live_voice=LiveVoiceConfig(
            intake_agent_id="synthetic-intake-agent",
            precall_secret="p" * 32,
            agent_config_version="2026-07-19.1",
        ),
    )
    configured_app = create_app(settings)
    headers = {"x-veramove-precall-secret": "p" * 32}
    first_request = {
        "agent_id": "synthetic-intake-agent",
        "call_sid": "CA-synthetic-replayed",
        "caller_id": "+15550101001",
        "called_number": "+15550101002",
    }

    with TestClient(configured_app) as test_client:
        first = test_client.post(
            "/api/webhooks/elevenlabs/pre-call",
            json=first_request,
            headers=headers,
        )
        replay = test_client.post(
            "/api/webhooks/elevenlabs/pre-call",
            json={
                **first_request,
                "caller_id": "+15550101003",
                "called_number": "+15550101004",
            },
            headers=headers,
        )
        other = test_client.post(
            "/api/webhooks/elevenlabs/pre-call",
            json={**first_request, "call_sid": "CA-synthetic-other"},
            headers=headers,
        )
        wrong_agent = test_client.post(
            "/api/webhooks/elevenlabs/pre-call",
            json={**first_request, "agent_id": "synthetic-wrong-agent"},
            headers=headers,
        )

        assert first.status_code == 200
        assert first.json() == replay.json()
        assert set(first.json()) == {"type", "dynamic_variables"}
        assert first.json()["type"] == "conversation_initiation_client_data"
        variables = first.json()["dynamic_variables"]
        assert set(variables) == {
            "job_id",
            "intake_session_id",
            "agent_config_version",
        }
        assert variables["agent_config_version"] == "2026-07-19.1"
        assert "prompt" not in first.json()
        assert other.status_code == 200
        other_variables = other.json()["dynamic_variables"]
        assert other_variables["job_id"] != variables["job_id"]
        assert other_variables["intake_session_id"] != variables["intake_session_id"]
        assert wrong_agent.status_code == 400

        session_id = variables["intake_session_id"]
        pending = test_client.get(f"/api/intake/sessions/{session_id}")
        assert pending.status_code == 200
        assert pending.json()["status"] == "pending"
        assert pending.json()["job_spec"] is None

        session_service = IntakeSessionService(
            repository=configured_app.state.repository,
            expected_agent_id="synthetic-intake-agent",
            agent_config_version="2026-07-19.1",
        )
        session_service.attach_conversation(
            session_id,
            "synthetic-conversation-id",
            agent_id="synthetic-intake-agent",
        )
        by_conversation = test_client.get("/api/intake/conversations/synthetic-conversation-id")
        assert by_conversation.status_code == 200
        assert by_conversation.json()["status"] == "in_progress"

        draft = job_spec.model_copy(
            update={
                "job_id": UUID(variables["job_id"]),
                "intake_source": IntakeSource.VOICE,
                "confirmed": False,
                "confirmed_at": None,
                "locked_version": None,
                "data_classification": DataClassification.ROLE_PLAY,
            },
            deep=True,
        )
        configured_app.state.repository.create(
            JobRecord(
                job_spec=draft,
                state=JobState.INTAKE_COMPLETE,
                created_at=session_service.clock(),
                updated_at=session_service.clock(),
            )
        )
        session_service.complete_session(session_id, "synthetic-conversation-id")
        completed = test_client.get(f"/api/intake/sessions/{session_id}")

    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["job_spec"]["job_id"] == variables["job_id"]
    serialized = repr(configured_app.state.repository._intake_sessions)
    for forbidden in (
        "CA-synthetic-replayed",
        "+15550101001",
        "+15550101002",
        "+15550101003",
        "+15550101004",
    ):
        assert forbidden not in serialized


def test_elevenlabs_webhook_is_idempotent(client):
    payload = {
        "idempotency_key": "synthetic-webhook-1",
        "event_type": "synthetic.call.completed",
        "payload": {"synthetic": True},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {
        "content-type": "application/json",
        "elevenlabs-signature": sign_webhook(body),
    }
    first = client.post("/api/webhooks/elevenlabs", content=body, headers=headers)
    second = client.post("/api/webhooks/elevenlabs", content=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"accepted": True, "duplicate": False}
    assert second.json() == {"accepted": False, "duplicate": True}


def test_invalid_webhook_signature_is_401(client):
    payload = {
        "idempotency_key": "synthetic-webhook-invalid-signature",
        "event_type": "synthetic.call.completed",
        "payload": {"synthetic": True},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    response = client.post(
        "/api/webhooks/elevenlabs",
        content=body,
        headers={
            "content-type": "application/json",
            "elevenlabs-signature": "bad",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "webhook_authentication_error"


def test_webhook_payload_error_is_logged_without_request_body(client, caplog):
    body = b'{"synthetic_private_value":'
    headers = {
        "content-type": "application/json",
        "elevenlabs-signature": sign_webhook(body),
    }

    with caplog.at_level(logging.WARNING, logger="services.api.app.main"):
        response = client.post("/api/webhooks/elevenlabs", content=body, headers=headers)

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "webhook_payload_error",
        "message": "ElevenLabs webhook body must be valid JSON",
    }
    assert caplog.messages == [
        "domain_error code=webhook_payload_error status_code=400 "
        "detail=ElevenLabs webhook body must be valid JSON"
    ]
    assert "synthetic_private_value" not in caplog.text


def test_vendor_discovery_returns_three_synthetic_vendors(client):
    response = client.get(
        "/api/vendors/discover",
        params={"origin": "Synthetic origin", "destination": "Synthetic destination"},
    )
    assert response.status_code == 200
    assert response.json()["source"] == "synthetic_mock"
    assert len(response.json()["vendors"]) == 3


def test_job_vendor_research_discovers_selects_and_builds_targeted_questions(
    client,
    job_spec_payload,
):
    job_spec_payload["origin"]["address_summary"] = "Cambridge, MA"
    job_spec_payload["destination"]["address_summary"] = "Somerville, MA"
    created = client.post("/api/jobs", json=job_spec_payload)
    job_id = created.json()["job_spec"]["job_id"]
    assert client.post(f"/api/jobs/{job_id}/confirm").status_code == 200

    discovered = client.post(f"/api/jobs/{job_id}/vendor-research/discover")
    assert discovered.status_code == 200
    assert discovered.json()["source"] == "synthetic_mock"
    vendor_ids = [vendor["vendor_id"] for vendor in discovered.json()["candidates"]]

    shortlisted = client.put(
        f"/api/jobs/{job_id}/vendor-research/shortlist",
        json={"vendor_ids": vendor_ids},
    )
    assert shortlisted.status_code == 200
    assert shortlisted.json()["selected_vendor_ids"] == vendor_ids

    analyzed = client.post(f"/api/jobs/{job_id}/vendor-research/analyze")
    assert analyzed.status_code == 200
    assert [item["status"] for item in analyzed.json()["dossiers"]] == [
        "complete",
        "complete",
        "complete",
    ]
    for dossier in analyzed.json()["dossiers"]:
        assert dossier["claims"][0]["classification"] == (
            "unverified_website_claim"
        )
        assert dossier["verification_questions"]
        assert dossier["missing_fee_categories"]

    fetched = client.get(f"/api/jobs/{job_id}/vendor-research")
    assert fetched.json() == analyzed.json()

    cleared = client.delete(
        f"/api/jobs/{job_id}/vendor-research/shortlist"
    )
    assert cleared.status_code == 200
    assert cleared.json()["selected_vendor_ids"] == []
    assert cleared.json()["dossiers"] == []


def test_job_vendor_research_requires_confirmation(client, job_spec_payload):
    created = client.post("/api/jobs", json=job_spec_payload)
    job_id = created.json()["job_spec"]["job_id"]

    response = client.post(f"/api/jobs/{job_id}/vendor-research/discover")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "domain_conflict"
