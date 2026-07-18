"""HTTP contract and mock-flow tests."""

from uuid import uuid4


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "mock",
        "service": "veramove-api",
    }


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


def test_elevenlabs_webhook_is_idempotent(client):
    payload = {
        "idempotency_key": "synthetic-webhook-1",
        "event_type": "synthetic.call.completed",
        "payload": {"synthetic": True},
    }
    first = client.post("/api/webhooks/elevenlabs", json=payload)
    second = client.post("/api/webhooks/elevenlabs", json=payload)
    assert first.json() == {"accepted": True, "duplicate": False}
    assert second.json() == {"accepted": False, "duplicate": True}


def test_vendor_discovery_returns_three_synthetic_vendors(client):
    response = client.get(
        "/api/vendors/discover",
        params={"origin": "Synthetic origin", "destination": "Synthetic destination"},
    )
    assert response.status_code == 200
    assert response.json()["source"] == "synthetic_mock"
    assert len(response.json()["vendors"]) == 3
