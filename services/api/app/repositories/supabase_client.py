"""Minimal server-only PostgREST client for Supabase persistence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from services.api.app.core.errors import ProviderRequestError

_ALLOWED_TABLES = frozenset(
    {
        "jobs",
        "intake_sessions",
        "vendors",
        "call_attempts",
        "calls",
        "quotes",
        "transcript_evidence",
        "recommendations",
        "event_log",
    }
)
_ALLOWED_RPCS = frozenset(
    {
        "veramove_claim_voice_webhook_receipt",
        "veramove_fail_voice_webhook_receipt",
        "veramove_finalize_voice_intake_webhook",
        "veramove_finalize_voice_webhook",
        "veramove_reserve_browser_voice_credential",
    }
)
_FORBIDDEN_VOICE_KEYS = frozenset(
    {
        "analysis",
        "api_key",
        "audio",
        "from_number",
        "phone",
        "phone_number",
        "raw_body",
        "raw_payload",
        "secret",
        "to_number",
        "transcript",
    }
)
_PHONE_LIKE = re.compile(r"\+[1-9]\d{7,14}")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_FILTER_OPERATORS = frozenset({"eq", "neq", "gt", "gte", "lt", "lte", "in", "is"})
_MAX_FILTERS = 20
_MAX_FILTER_LENGTH = 500
_SELECT_LIMIT = 1000


class SupabaseDuplicate(Exception):
    """Internal signal that a Postgres uniqueness constraint rejected a row."""


@dataclass(frozen=True, slots=True)
class SupabaseHttpResponse:
    """Parsed low-level response without exposing HTTPX internals upstream."""

    status_code: int
    body: Any


class SupabaseJsonTransport(Protocol):
    """Injected HTTP boundary used by the PostgREST client."""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        payload: dict[str, Any] | None,
        timeout_seconds: float,
    ) -> SupabaseHttpResponse: ...


class SupabaseTableClient(Protocol):
    """Table operations consumed by the persistent repository."""

    def select_many(
        self,
        table: str,
        filters: dict[str, str],
    ) -> list[dict[str, Any]]: ...

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]: ...

    def upsert(
        self,
        table: str,
        row: dict[str, Any],
        on_conflict: str,
    ) -> dict[str, Any]: ...

    def update(
        self,
        table: str,
        filters: dict[str, str],
        values: dict[str, Any],
    ) -> dict[str, Any]: ...

    def rpc(self, name: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class HttpxSupabaseTransport:
    """Bounded synchronous HTTP transport used only by the backend."""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        payload: dict[str, Any] | None,
        timeout_seconds: float,
    ) -> SupabaseHttpResponse:
        try:
            response = httpx.request(
                method,
                url,
                headers=headers,
                params=params,
                json=payload,
                timeout=timeout_seconds,
            )
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError("Supabase request failed") from exc
        return SupabaseHttpResponse(status_code=response.status_code, body=body)


class SupabasePostgrestClient:
    """Allowlisted Supabase Data API table client with safe error mapping."""

    def __init__(
        self,
        url: str,
        secret_key: str,
        transport: SupabaseJsonTransport | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._secret_key = secret_key
        self._transport = transport or HttpxSupabaseTransport()

    def select_many(
        self,
        table: str,
        filters: dict[str, str],
    ) -> list[dict[str, Any]]:
        self._validate_table(table)
        self._validate_filters(filters)
        body = self._request(
            "GET",
            table,
            params={
                **filters,
                "select": "*",
                "limit": str(_SELECT_LIMIT),
            },
        )
        if not isinstance(body, list) or not all(isinstance(row, dict) for row in body):
            raise ProviderRequestError("Supabase request failed")
        return body

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        self._validate_table(table)
        return self._mutation(
            "POST",
            table,
            row,
            prefer="return=representation",
        )

    def upsert(
        self,
        table: str,
        row: dict[str, Any],
        on_conflict: str,
    ) -> dict[str, Any]:
        self._validate_table(table)
        self._validate_identifier(on_conflict)
        return self._mutation(
            "POST",
            table,
            row,
            params={"on_conflict": on_conflict},
            prefer="resolution=merge-duplicates,return=representation",
        )

    def update(
        self,
        table: str,
        filters: dict[str, str],
        values: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_table(table)
        self._validate_filters(filters)
        return self._mutation(
            "PATCH",
            table,
            values,
            params=filters,
            prefer="return=representation",
        )

    def rpc(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Call one allowlisted transactional function with a bounded safe payload."""

        if name not in _ALLOWED_RPCS:
            raise ValueError("Supabase RPC is not allowed")
        self._validate_rpc_payload(payload)
        body = self._request(
            "POST",
            f"rpc/{name}",
            params={},
            payload=payload,
        )
        if not isinstance(body, dict):
            raise ProviderRequestError("Supabase request failed")
        return body

    def _mutation(
        self,
        method: str,
        table: str,
        payload: dict[str, Any],
        *,
        params: dict[str, str] | None = None,
        prefer: str,
    ) -> dict[str, Any]:
        body = self._request(
            method,
            table,
            params=params or {},
            payload=payload,
            prefer=prefer,
        )
        if not isinstance(body, list) or len(body) != 1 or not isinstance(body[0], dict):
            raise ProviderRequestError("Supabase request failed")
        return body[0]

    def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str],
        payload: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> Any:
        headers = {
            "apikey": self._secret_key,
            "Authorization": f"Bearer {self._secret_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer is not None:
            headers["Prefer"] = prefer
        try:
            response = self._transport.request(
                method,
                f"{self._url}/rest/v1/{table}",
                headers,
                params,
                payload,
                timeout_seconds=10.0,
            )
        except ProviderRequestError:
            raise
        except Exception as exc:
            raise ProviderRequestError("Supabase request failed") from exc

        if response.status_code == 409 and self._is_unique_violation(response.body):
            raise SupabaseDuplicate("Supabase row already exists")
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderRequestError("Supabase request failed")
        if not isinstance(response.body, (dict, list)):
            raise ProviderRequestError("Supabase request failed")
        return response.body

    @staticmethod
    def _is_unique_violation(body: Any) -> bool:
        return isinstance(body, dict) and body.get("code") == "23505"

    @staticmethod
    def _validate_table(table: str) -> None:
        if table not in _ALLOWED_TABLES:
            raise ValueError("Supabase table is not allowed")

    @classmethod
    def _validate_rpc_payload(cls, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Invalid Supabase RPC payload")

        def inspect(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if not isinstance(key, str) or key.casefold() in _FORBIDDEN_VOICE_KEYS:
                        raise ValueError("Unsafe Supabase RPC payload")
                    inspect(item)
                return
            if isinstance(value, list):
                if len(value) > 1_000:
                    raise ValueError("Supabase RPC payload is too large")
                for item in value:
                    inspect(item)
                return
            if isinstance(value, str) and _PHONE_LIKE.search(value) is not None:
                raise ValueError("Unsafe Supabase RPC payload")

        inspect(payload)
        if len(json.dumps(payload, separators=(",", ":"), default=str)) > 1_000_000:
            raise ValueError("Supabase RPC payload is too large")

    @classmethod
    def _validate_filters(cls, filters: dict[str, str]) -> None:
        if len(filters) > _MAX_FILTERS:
            raise ValueError("Too many Supabase filters")
        for key, value in filters.items():
            cls._validate_identifier(key)
            if not isinstance(value, str) or len(value) > _MAX_FILTER_LENGTH:
                raise ValueError("Invalid Supabase filter")
            operator, separator, _operand = value.partition(".")
            if not separator or operator not in _FILTER_OPERATORS:
                raise ValueError("Invalid Supabase filter")

    @staticmethod
    def _validate_identifier(value: str) -> None:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("Invalid Supabase identifier")


__all__ = [
    "HttpxSupabaseTransport",
    "SupabaseDuplicate",
    "SupabaseHttpResponse",
    "SupabaseJsonTransport",
    "SupabasePostgrestClient",
    "SupabaseTableClient",
]
