"""Canonical OpenAPI export tests."""

import json

from scripts.export_openapi import export_openapi


def test_export_openapi_contains_required_routes_and_schemas(tmp_path):
    target = export_openapi(tmp_path / "openapi.json")
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["info"]["title"] == "VeraMove API"
    for path in (
        "/health",
        "/api/integrations/status",
        "/api/intake/document",
        "/api/intake/sessions",
        "/api/intake/sessions/{session_id}",
        "/api/intake/sessions/{session_id}/voice-token",
        "/api/intake/sessions/{session_id}/conversation",
        "/api/intake/conversations/{conversation_id}",
        "/api/jobs",
        "/api/jobs/{job_id}",
        "/api/jobs/{job_id}/events",
        "/api/jobs/{job_id}/confirm",
        "/api/jobs/{job_id}/vendor-research",
        "/api/jobs/{job_id}/vendor-research/discover",
        "/api/jobs/{job_id}/vendor-research/shortlist",
        "/api/jobs/{job_id}/vendor-research/analyze",
        "/api/jobs/{job_id}/calls",
        "/api/jobs/{job_id}/negotiate",
        "/api/jobs/{job_id}/report",
        "/api/calls/{call_id}/recording",
        "/api/calls/{call_id}/repair",
        "/api/webhooks/elevenlabs",
        "/api/webhooks/elevenlabs/pre-call",
        "/api/vendors/discover",
    ):
        assert path in document["paths"]
    for schema in ("JobSpecV1", "QuoteV1", "CallRecord", "RecommendationV1"):
        assert schema in document["components"]["schemas"]
    for schema in (
        "DocumentIntakeRequest",
        "HealthResponse",
        "RuntimeHealthResponse",
        "JobEventsResponse",
        "ElevenLabsPostCallWebhook",
        "ElevenLabsConversationInitiationResponse",
        "IntakeSessionResponse",
        "AttachIntakeConversationRequest",
        "BrowserVoiceTokenResponse",
        "IntegrationStatusSnapshot",
        "JobVendorResearchV1",
        "VendorShortlistRequest",
    ):
        assert schema in document["components"]["schemas"]

    webhook_schema = document["paths"]["/api/webhooks/elevenlabs"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    assert webhook_schema == {
        "anyOf": [
            {"$ref": "#/components/schemas/ElevenLabsWebhookEvent"},
            {"$ref": "#/components/schemas/ElevenLabsPostCallWebhook"},
        ]
    }
    recording = document["components"]["schemas"]["CallRecord"]["properties"][
        "recording_url"
    ]
    assert {item.get("type") for item in recording["anyOf"]} == {"string", "null"}
