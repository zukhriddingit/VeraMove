"""Canonical OpenAPI export tests."""

import json

from scripts.export_openapi import export_openapi


def test_export_openapi_contains_required_routes_and_schemas(tmp_path):
    target = export_openapi(tmp_path / "openapi.json")
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["info"]["title"] == "VeraMove API"
    for path in (
        "/health",
        "/api/intake/document",
        "/api/jobs",
        "/api/jobs/{job_id}",
        "/api/jobs/{job_id}/events",
        "/api/jobs/{job_id}/confirm",
        "/api/jobs/{job_id}/calls",
        "/api/jobs/{job_id}/negotiate",
        "/api/jobs/{job_id}/report",
        "/api/webhooks/elevenlabs",
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
    ):
        assert schema in document["components"]["schemas"]
