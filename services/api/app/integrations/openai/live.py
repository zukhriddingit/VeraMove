"""Fail-closed OpenAI Responses adapters with injected HTTP transports."""

from __future__ import annotations

import base64
import json
from copy import deepcopy
from typing import Any

import httpx

from services.api.app.contracts import (
    DocumentParseResult,
    IntelligenceFinding,
    JobSpecV1,
    RecommendationRanking,
)
from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.openai.base import OpenAIJsonTransport

NARRATIVE_SYSTEM_PROMPT = """\
Explain the already-determined VeraMove ranking. Preserve vendor order, totals,
findings, and evidence identifiers. Do not add facts, quotes, discounts, claims,
or recommendations not present in the supplied structured data. Return only a
concise customer-facing summary.
"""


def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return an OpenAI-strict copy without mutating Pydantic's schema."""

    strict_schema = deepcopy(schema)

    def normalize(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                normalize(item)
            return
        if not isinstance(node, dict):
            return

        node.pop("default", None)
        properties = node.get("properties")
        if node.get("type") == "object" and isinstance(properties, dict):
            node["required"] = list(properties)
        for value in node.values():
            normalize(value)

    normalize(strict_schema)
    return strict_schema


class HttpxOpenAITransport:
    """Send one JSON request while translating details into safe errors."""

    def post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError("OpenAI request failed") from exc
        if not isinstance(result, dict):
            raise ProviderRequestError(
                "OpenAI returned an invalid response envelope"
            )
        return result


class _OpenAIResponsesBase:
    def __init__(
        self,
        api_key: str,
        api_base_url: str = "https://api.openai.com",
        transport: OpenAIJsonTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_base_url = api_base_url.rstrip("/")
        self._transport = transport or HttpxOpenAITransport()

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._transport.post(
            f"{self._api_base_url}/v1/responses",
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            payload,
        )

    @staticmethod
    def _output_text(response: dict[str, Any]) -> str:
        if response.get("status") != "completed":
            raise ProviderRequestError("OpenAI response was not completed")
        output = response.get("output")
        if not isinstance(output, list):
            raise ProviderRequestError("OpenAI returned malformed output")

        texts: list[str] = []
        refusal_found = False
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                raise ProviderRequestError("OpenAI returned malformed output")
            for part in content:
                if not isinstance(part, dict):
                    raise ProviderRequestError("OpenAI returned malformed output")
                if part.get("type") == "refusal":
                    refusal_found = True
                elif part.get("type") == "output_text":
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text)
                    else:
                        raise ProviderRequestError(
                            "OpenAI returned empty output text"
                        )

        if refusal_found:
            raise ProviderRequestError("OpenAI refused the request")
        if len(texts) != 1:
            raise ProviderRequestError(
                "OpenAI response must contain exactly one output text"
            )
        return texts[0]


class OpenAIResponsesClient(_OpenAIResponsesBase):
    """Extract a strict document result through the Responses API."""

    def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        content: bytes,
        mime_type: str,
        source_id: str,
        response_schema: type[DocumentParseResult],
    ) -> dict[str, Any]:
        response = self._post(
            {
                "model": model,
                "reasoning": {"effort": "none"},
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {"type": "input_text", "text": system_prompt}
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            self._content_part(content, mime_type, source_id)
                        ],
                    },
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "document_parse_result",
                        "strict": True,
                        "schema": _strict_json_schema(
                            response_schema.model_json_schema()
                        ),
                    }
                },
            }
        )
        try:
            result = json.loads(self._output_text(response))
        except json.JSONDecodeError as exc:
            raise ProviderRequestError(
                "OpenAI returned invalid structured output"
            ) from exc
        if not isinstance(result, dict):
            raise ProviderRequestError("OpenAI returned invalid structured output")
        return result

    @staticmethod
    def _content_part(
        content: bytes,
        mime_type: str,
        source_id: str,
    ) -> dict[str, Any]:
        if mime_type == "text/plain":
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProviderRequestError(
                    "OpenAI document text must be valid UTF-8"
                ) from exc
            return {"type": "input_text", "text": text}

        encoded = base64.b64encode(content).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded}"
        if mime_type == "application/pdf":
            return {
                "type": "input_file",
                "filename": source_id,
                "file_data": data_url,
            }
        if mime_type in {"image/png", "image/jpeg"}:
            return {
                "type": "input_image",
                "image_url": data_url,
                "detail": "low",
            }
        raise ProviderRequestError("OpenAI received an unsupported document type")


class OpenAIResponsesNarrativeClient(_OpenAIResponsesBase):
    """Narrate immutable deterministic recommendation inputs as plain text."""

    def explain(
        self,
        *,
        model: str,
        job_spec: JobSpecV1,
        rankings: list[RecommendationRanking],
        findings: list[IntelligenceFinding],
    ) -> str:
        grounded_input = json.dumps(
            {
                "job_spec": job_spec.model_dump(mode="json"),
                "rankings": [
                    ranking.model_dump(mode="json") for ranking in rankings
                ],
                "findings": [
                    finding.model_dump(mode="json") for finding in findings
                ],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        response = self._post(
            {
                "model": model,
                "reasoning": {"effort": "none"},
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": NARRATIVE_SYSTEM_PROMPT,
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": grounded_input}
                        ],
                    },
                ],
                "text": {"format": {"type": "text"}},
            }
        )
        return self._output_text(response)
