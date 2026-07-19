"""Safe, transport-injected Supabase Data API client tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from services.api.app.core.errors import ProviderRequestError
from services.api.app.repositories.supabase_client import (
    SupabaseDuplicate,
    SupabaseHttpResponse,
    SupabasePostgrestClient,
)


@dataclass
class RecordingTransport:
    response: SupabaseHttpResponse | Exception

    def __post_init__(self) -> None:
        self.requests: list[
            tuple[
                str,
                str,
                dict[str, str],
                dict[str, str],
                dict[str, Any] | None,
            ]
        ] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        payload: dict[str, Any] | None,
        timeout_seconds: float,
    ) -> SupabaseHttpResponse:
        assert timeout_seconds == 10.0
        self.requests.append((method, url, headers, params, payload))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def make_client(transport: RecordingTransport) -> SupabasePostgrestClient:
    return SupabasePostgrestClient(
        url="https://synthetic.supabase.co",
        secret_key="synthetic-secret",
        transport=transport,
    )


def test_postgrest_client_sends_backend_headers_and_bounded_filters():
    transport = RecordingTransport(
        SupabaseHttpResponse(200, [{"id": "synthetic-id", "payload": {}}])
    )
    rows = make_client(transport).select_many(
        "jobs",
        {"id": "eq.synthetic-id"},
    )

    assert len(rows) == 1
    method, url, headers, params, payload = transport.requests[0]
    assert method == "GET"
    assert url == "https://synthetic.supabase.co/rest/v1/jobs"
    assert headers["apikey"] == "synthetic-secret"
    assert headers["Authorization"] == "Bearer synthetic-secret"
    assert params == {
        "id": "eq.synthetic-id",
        "select": "*",
        "limit": "1000",
    }
    assert payload is None
    assert "synthetic-secret" not in repr(rows)


@pytest.mark.parametrize(
    ("operation", "expected_method", "expected_prefer"),
    [
        ("insert", "POST", "return=representation"),
        (
            "upsert",
            "POST",
            "resolution=merge-duplicates,return=representation",
        ),
        ("update", "PATCH", "return=representation"),
    ],
)
def test_postgrest_mutations_request_representations(
    operation,
    expected_method,
    expected_prefer,
):
    transport = RecordingTransport(
        SupabaseHttpResponse(200, [{"id": "synthetic-id", "payload": {}}])
    )
    client = make_client(transport)
    if operation == "insert":
        row = client.insert("jobs", {"id": "synthetic-id", "payload": {}})
    elif operation == "upsert":
        row = client.upsert(
            "jobs",
            {"id": "synthetic-id", "payload": {}},
            on_conflict="id",
        )
    else:
        row = client.update(
            "jobs",
            {"id": "eq.synthetic-id"},
            {"payload": {}},
        )

    assert row["id"] == "synthetic-id"
    method, _url, headers, params, _payload = transport.requests[0]
    assert method == expected_method
    assert headers["Prefer"] == expected_prefer
    if operation == "upsert":
        assert params == {"on_conflict": "id"}
    elif operation == "update":
        assert params == {"id": "eq.synthetic-id"}


def test_postgrest_unique_violation_has_dedicated_safe_exception():
    transport = RecordingTransport(
        SupabaseHttpResponse(
            409,
            {
                "code": "23505",
                "message": "duplicate includes synthetic-secret and raw payload",
            },
        )
    )

    with pytest.raises(SupabaseDuplicate) as raised:
        make_client(transport).insert(
            "event_log",
            {"id": "synthetic-id", "payload": {}},
        )

    assert str(raised.value) == "Supabase row already exists"
    assert "synthetic-secret" not in str(raised.value)


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_postgrest_errors_are_safe(status):
    transport = RecordingTransport(
        SupabaseHttpResponse(
            status,
            {"message": "provider leaked synthetic-secret and private payload"},
        )
    )

    with pytest.raises(ProviderRequestError, match="Supabase request failed") as raised:
        make_client(transport).select_many("jobs", {})

    assert "synthetic-secret" not in str(raised.value)
    assert "private payload" not in str(raised.value)


def test_postgrest_transport_and_malformed_json_fail_safely():
    network = RecordingTransport(TimeoutError("synthetic-secret"))
    with pytest.raises(ProviderRequestError, match="Supabase request failed"):
        make_client(network).select_many("jobs", {})

    malformed = RecordingTransport(SupabaseHttpResponse(200, "not-json-object-or-array"))
    with pytest.raises(ProviderRequestError, match="Supabase request failed"):
        make_client(malformed).select_many("jobs", {})


@pytest.mark.parametrize(
    ("table", "filters"),
    [
        ("private_table", {}),
        ("jobs", {"bad column": "eq.value"}),
        ("jobs", {"id": "contains.unbounded"}),
        ("jobs", {f"field_{index}": "eq.value" for index in range(21)}),
    ],
)
def test_postgrest_rejects_unapproved_or_unbounded_queries(table, filters):
    transport = RecordingTransport(SupabaseHttpResponse(200, []))

    with pytest.raises(ValueError):
        make_client(transport).select_many(table, filters)

    assert transport.requests == []


def test_postgrest_rpc_calls_only_allowlisted_transactional_functions():
    transport = RecordingTransport(SupabaseHttpResponse(200, {"claimed": True, "processed": False}))
    payload = {
        "p_idempotency_key": "synthetic-event-key",
        "p_event_type": "post_call_transcription",
        "p_lease_token": "11111111-1111-4111-8111-111111111111",
        "p_lease_expires_at": "2026-07-19T12:05:00Z",
        "p_now": "2026-07-19T12:00:00Z",
    }

    result = make_client(transport).rpc(
        "veramove_claim_voice_webhook_receipt",
        payload,
    )

    assert result == {"claimed": True, "processed": False}
    method, url, _headers, params, sent = transport.requests[0]
    assert method == "POST"
    assert url == ("https://synthetic.supabase.co/rest/v1/rpc/veramove_claim_voice_webhook_receipt")
    assert params == {}
    assert sent == payload

    with pytest.raises(ValueError, match="not allowed"):
        make_client(transport).rpc("execute_arbitrary_sql", {})
    assert len(transport.requests) == 1


def test_postgrest_allows_typed_intake_transaction_rpc():
    transport = RecordingTransport(
        SupabaseHttpResponse(200, {"processed": True, "duplicate": False})
    )
    payload = {
        "p_idempotency_key": "synthetic-intake-event-key",
        "p_lease_token": "11111111-1111-4111-8111-111111111111",
        "p_kind": "failed",
        "p_session": {
            "id": "22222222-2222-4222-8222-222222222222",
            "reserved_job_id": "33333333-3333-4333-8333-333333333333",
            "status": "failed",
            "failure_code": "provider_no_answer",
        },
        "p_job": None,
        "p_event": {"event_type": "call_initiation_failure"},
        "p_now": "2026-07-19T12:00:00Z",
    }

    result = make_client(transport).rpc(
        "veramove_finalize_voice_intake_webhook",
        payload,
    )

    assert result == {"processed": True, "duplicate": False}
    method, url, _headers, params, sent = transport.requests[0]
    assert method == "POST"
    assert url.endswith("/rest/v1/rpc/veramove_finalize_voice_intake_webhook")
    assert params == {}
    assert sent == payload


@pytest.mark.parametrize(
    "unsafe_fragment",
    (
        {"transcript": "private call text"},
        {"analysis": {"summary": "private"}},
        {"to_number": "+15550100001"},
        {"nested": {"phone": "+15550100001"}},
        {"nested": {"safe_label": "+15550100001"}},
        {"api_key": "synthetic-secret"},
        {"audio": "base64-private"},
    ),
)
def test_postgrest_finalize_rpc_rejects_sensitive_or_phone_payloads(unsafe_fragment):
    transport = RecordingTransport(SupabaseHttpResponse(200, {"processed": True}))
    payload = {
        "p_idempotency_key": "synthetic-event-key",
        "p_lease_token": "11111111-1111-4111-8111-111111111111",
        "p_attempt": {"payload": unsafe_fragment},
    }

    with pytest.raises(ValueError, match="Unsafe"):
        make_client(transport).rpc("veramove_finalize_voice_webhook", payload)

    assert transport.requests == []
