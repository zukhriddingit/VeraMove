"""OpenAI Responses adapters without external network calls."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import httpx
import pytest

from services.api.app.contracts import DocumentParseResult, IntakeSource
from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.openai.document import OpenAIDocumentParser
from services.api.app.integrations.openai.live import (
    HttpxOpenAITransport,
    OpenAIResponsesClient,
    OpenAIResponsesNarrativeClient,
)
from services.api.app.observability.usage import UsageRecord, UsageRecorder


class RecordingTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.requests: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.requests.append((url, headers, payload))
        return self.response


def completed_response_text(text: str) -> dict[str, Any]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


def completed_response(payload: dict[str, Any]) -> dict[str, Any]:
    return completed_response_text(json.dumps(payload))


def document_result(fixtures) -> dict[str, Any]:
    job_spec = fixtures.load_job().model_copy(
        update={
            "intake_source": IntakeSource.DOCUMENT,
            "move_date": None,
            "confirmed": False,
            "confirmed_at": None,
            "locked_version": None,
        },
        deep=True,
    )
    return {
        "job_spec": job_spec.model_dump(mode="json"),
        "missing_fields": job_spec.missing_required_fields(),
        "warnings": [],
        "fields_requiring_confirmation": [],
        "provenance": [],
    }


def contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(contains_key(item, key) for item in value)
    return False


def test_openai_document_request_uses_strict_responses_schema(fixtures):
    result = document_result(fixtures)
    transport = RecordingTransport(completed_response(result))
    client = OpenAIResponsesClient(
        api_key="synthetic-openai-key",
        api_base_url="https://api.openai.example",
        transport=transport,
    )

    parsed = client.parse(
        model="gpt-5.6-luna",
        system_prompt="Extract supported facts.",
        content=b"SYNTHETIC two-bedroom move",
        mime_type="text/plain",
        source_id="synthetic.txt",
        response_schema=DocumentParseResult,
    )

    assert parsed == result
    url, headers, payload = transport.requests[0]
    assert url == "https://api.openai.example/v1/responses"
    assert headers["Authorization"] == "Bearer synthetic-openai-key"
    assert payload["reasoning"] == {"effort": "none"}
    assert payload["text"]["format"]["strict"] is True
    schema = payload["text"]["format"]["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    job_spec_schema = schema["$defs"]["JobSpecV1"]
    assert set(job_spec_schema["required"]) == set(job_spec_schema["properties"])
    assert not contains_key(schema, "default")
    for unsupported in (
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "multipleOf",
        "patternProperties",
        "minItems",
        "maxItems",
    ):
        assert not contains_key(schema, unsupported)
    assert payload["input"][1]["content"] == [
        {
            "type": "input_text",
            "text": "SYNTHETIC two-bedroom move",
        }
    ]


@pytest.mark.parametrize(
    "response",
    [
        {"status": "incomplete", "output": []},
        {"status": "completed", "output": []},
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal"}],
                }
            ],
        },
    ],
)
def test_openai_rejects_incomplete_empty_or_refused_output(response):
    client = OpenAIResponsesClient(
        api_key="synthetic",
        transport=RecordingTransport(response),
    )

    with pytest.raises(ProviderRequestError):
        client.parse(
            model="gpt-5.6-luna",
            system_prompt="Synthetic prompt",
            content=b"synthetic",
            mime_type="text/plain",
            source_id="synthetic.txt",
            response_schema=DocumentParseResult,
        )


def test_openai_rejects_invalid_json_output():
    client = OpenAIResponsesClient(
        api_key="synthetic",
        transport=RecordingTransport(completed_response_text("not-json")),
    )

    with pytest.raises(ProviderRequestError, match="invalid structured output"):
        client.parse(
            model="gpt-5.6-luna",
            system_prompt="Synthetic prompt",
            content=b"synthetic",
            mime_type="text/plain",
            source_id="synthetic.txt",
            response_schema=DocumentParseResult,
        )


@pytest.mark.parametrize("status_code", [401, 429, 503])
def test_http_transport_maps_provider_statuses_to_safe_errors(
    monkeypatch,
    status_code,
):
    def fake_post(*args, **kwargs):
        return httpx.Response(
            status_code,
            json={"provider_detail": "must not leak"},
            request=httpx.Request("POST", "https://api.openai.example"),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(ProviderRequestError) as caught:
        HttpxOpenAITransport().post(
            "https://api.openai.example/v1/responses",
            {"Authorization": "Bearer synthetic-secret"},
            {"sensitive": "synthetic document"},
        )

    message = str(caught.value)
    assert message == "OpenAI request failed"
    assert "synthetic-secret" not in message
    assert "must not leak" not in message


def test_http_transport_maps_timeout_to_safe_error(monkeypatch):
    def fake_post(*args, **kwargs):
        request = httpx.Request("POST", "https://api.openai.example")
        raise httpx.ConnectTimeout("synthetic timeout detail", request=request)

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(ProviderRequestError, match="OpenAI request failed"):
        HttpxOpenAITransport().post(
            "https://api.openai.example/v1/responses",
            {"Authorization": "Bearer synthetic-secret"},
            {"sensitive": "synthetic document"},
        )


def test_document_parser_supports_plain_text_and_enforces_postconditions(fixtures):
    result = document_result(fixtures)
    result["job_spec"]["job_id"] = "model-authored-job-id"
    for index, item in enumerate(result["job_spec"]["inventory"]):
        item["item_id"] = f"model-authored-item-{index}"
    model_supplied_job_id = result["job_spec"]["job_id"]
    model_supplied_item_ids = {
        item["item_id"] for item in result["job_spec"]["inventory"]
    }
    parser = OpenAIDocumentParser(
        OpenAIResponsesClient(
            api_key="synthetic",
            transport=RecordingTransport(completed_response(result)),
        ),
        model="gpt-5.6-luna",
    )

    parsed = parser.parse_document(
        b"SYNTHETIC two-bedroom move",
        "text/plain",
        "synthetic.txt",
    )

    assert parsed.job_spec.intake_source is IntakeSource.DOCUMENT
    assert parsed.job_spec.confirmed is False
    assert parsed.job_spec.confirmed_at is None
    assert parsed.job_spec.locked_version is None
    assert str(parsed.job_spec.job_id) != model_supplied_job_id
    assert not model_supplied_item_ids.intersection(
        str(item.item_id) for item in parsed.job_spec.inventory
    )

    second = parser.parse_document(
        b"SYNTHETIC two-bedroom move",
        "text/plain",
        "synthetic.txt",
    )
    assert second.job_spec.job_id != parsed.job_spec.job_id


def test_document_parser_normalizes_model_missing_fields_without_mutating_response(
    fixtures,
):
    result = document_result(fixtures)
    result["missing_fields"] = []
    result["warnings"] = ["Synthetic warning remains."]
    original = deepcopy(result)
    parser = OpenAIDocumentParser(
        OpenAIResponsesClient(
            api_key="synthetic",
            transport=RecordingTransport(completed_response(result)),
        ),
        model="gpt-5.6-luna",
    )

    parsed = parser.parse_document(
        b"SYNTHETIC two-bedroom move",
        "text/plain",
        "synthetic.txt",
    )

    assert parsed.missing_fields == parsed.job_spec.missing_required_fields()
    assert parsed.warnings == ["Synthetic warning remains."]
    assert result == original


def test_openai_document_binary_content_uses_data_urls(fixtures):
    result = document_result(fixtures)
    transport = RecordingTransport(completed_response(result))
    client = OpenAIResponsesClient(api_key="synthetic", transport=transport)

    client.parse(
        model="gpt-5.6-luna",
        system_prompt="Synthetic prompt",
        content=b"synthetic-pdf",
        mime_type="application/pdf",
        source_id="synthetic.pdf",
        response_schema=DocumentParseResult,
    )
    pdf_part = transport.requests[-1][2]["input"][1]["content"][0]
    assert pdf_part["type"] == "input_file"
    assert pdf_part["filename"] == "synthetic.pdf"
    assert pdf_part["file_data"].startswith("data:application/pdf;base64,")

    client.parse(
        model="gpt-5.6-luna",
        system_prompt="Synthetic prompt",
        content=b"synthetic-image",
        mime_type="image/png",
        source_id="synthetic.png",
        response_schema=DocumentParseResult,
    )
    image_part = transport.requests[-1][2]["input"][1]["content"][0]
    assert image_part["type"] == "input_image"
    assert image_part["detail"] == "low"
    assert image_part["image_url"].startswith("data:image/png;base64,")


def test_openai_narrative_request_is_grounded_and_cannot_mutate_inputs(fixtures):
    recommendation = fixtures.load_recommendation()
    rankings = recommendation.rankings
    findings = recommendation.hidden_fee_findings
    rankings_before = [ranking.model_dump(mode="json") for ranking in rankings]
    findings_before = [finding.model_dump(mode="json") for finding in findings]
    transport = RecordingTransport(
        completed_response_text("ClearPath remains the evidence-backed winner.")
    )
    client = OpenAIResponsesNarrativeClient(
        api_key="synthetic-openai-key",
        api_base_url="https://api.openai.example",
        transport=transport,
    )

    summary = client.explain(
        model="gpt-5.6-terra",
        job_spec=fixtures.load_job(),
        rankings=rankings,
        findings=findings,
    )

    assert summary == "ClearPath remains the evidence-backed winner."
    assert [ranking.model_dump(mode="json") for ranking in rankings] == rankings_before
    assert [finding.model_dump(mode="json") for finding in findings] == findings_before
    url, headers, payload = transport.requests[0]
    assert url == "https://api.openai.example/v1/responses"
    assert headers["Authorization"] == "Bearer synthetic-openai-key"
    assert payload["reasoning"] == {"effort": "none"}
    assert payload["text"] == {"format": {"type": "text"}}
    user_payload = json.loads(payload["input"][1]["content"][0]["text"])
    assert user_payload["rankings"] == rankings_before
    assert user_payload["findings"] == findings_before


def test_openai_clients_record_safe_usage_without_prompts_responses_or_secrets(fixtures):
    recorder = UsageRecorder()
    raw_document = "SYNTHETIC_PRIVATE_DOCUMENT_MARKER"
    secret = "synthetic-openai-secret-marker"
    document_response = completed_response(document_result(fixtures))
    document_response.update(
        {
            "id": "resp_synthetic_document",
            "usage": {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        }
    )
    document_client = OpenAIResponsesClient(
        api_key=secret,
        transport=RecordingTransport(document_response),
        usage_recorder=recorder,
    )

    document_client.parse(
        model="gpt-5.6-luna",
        system_prompt="SYNTHETIC_PRIVATE_PROMPT_MARKER",
        content=raw_document.encode(),
        mime_type="text/plain",
        source_id="synthetic.txt",
        response_schema=DocumentParseResult,
    )

    narrative_response = completed_response_text("SYNTHETIC_PRIVATE_RESPONSE_MARKER")
    narrative_response.update(
        {
            "id": "resp_synthetic_narrative",
            "usage": {"input_tokens": 80, "output_tokens": 12, "total_tokens": 92},
        }
    )
    recommendation = fixtures.load_recommendation()
    narrative_client = OpenAIResponsesNarrativeClient(
        api_key=secret,
        transport=RecordingTransport(narrative_response),
        usage_recorder=recorder,
    )
    narrative_client.explain(
        model="gpt-5.6-terra",
        job_spec=fixtures.load_job(),
        rankings=recommendation.rankings,
        findings=recommendation.hidden_fee_findings,
    )

    records = recorder.snapshot()
    assert [(record.capability, record.total_tokens) for record in records] == [
        ("document_extraction", 150),
        ("recommendation_narration", 92),
    ]
    assert [record.provider_request_id for record in records] == [
        "resp_synthetic_document",
        "resp_synthetic_narrative",
    ]
    serialized = json.dumps([record.model_dump(mode="json") for record in records])
    for sensitive in (
        raw_document,
        secret,
        "SYNTHETIC_PRIVATE_PROMPT_MARKER",
        "SYNTHETIC_PRIVATE_RESPONSE_MARKER",
    ):
        assert sensitive not in serialized


def test_usage_recorder_is_bounded_and_aggregates_safe_dimensions():
    recorder = UsageRecorder(max_records=2)
    for index, category in enumerate(("success", "provider_error", "success")):
        recorder.record(
            UsageRecord(
                capability="document_extraction",
                model="gpt-synthetic",
                input_tokens=index,
                output_tokens=1,
                total_tokens=index + 1,
                latency_ms=10,
                success_category=category,
            )
        )

    assert len(recorder.snapshot()) == 2
    aggregate = recorder.aggregates()[0]
    assert aggregate.request_count == 2
    assert aggregate.successful_requests == 1
    assert aggregate.failed_requests == 1
    assert aggregate.total_tokens == 5
