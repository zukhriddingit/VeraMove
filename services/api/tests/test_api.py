"""HTTP contract and mock-flow tests."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from services.api.app.main import create_app

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
    assert response.headers["access-control-allow-origin"] == (
        "https://veramove-demo.example"
    )


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
    assert len(report.json()["transcript_evidence"]) == 4
    assert all(item["recording_url"] for item in report.json()["transcript_evidence"])


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
    assert {
        item["outcome"]["type"] for item in first_calls.json()["calls"]
    } == {"itemized_quote"}
    assert {
        item["outcome"]["quote"]["job_spec_version"]
        for item in first_calls.json()["calls"]
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
    assert all(
        item["recording_url"] for item in report.json()["transcript_evidence"]
    )


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


def test_vendor_discovery_returns_three_synthetic_vendors(client):
    response = client.get(
        "/api/vendors/discover",
        params={"origin": "Synthetic origin", "destination": "Synthetic destination"},
    )
    assert response.status_code == 200
    assert response.json()["source"] == "synthetic_mock"
    assert len(response.json()["vendors"]) == 3
