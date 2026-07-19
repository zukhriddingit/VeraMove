"""Strict structured-output document intake without directly importing an SDK."""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from services.api.app.contracts import DocumentParseResult, IntakeSource, JobSpecV1
from services.api.app.integrations.openai.base import StructuredDocumentClient

SUPPORTED_DOCUMENT_TYPES = {
    "text/plain",
    "application/pdf",
    "image/png",
    "image/jpeg",
}

DOCUMENT_SYSTEM_PROMPT = """\
Extract only moving-job facts explicitly supported by the supplied document.
Return the strict DocumentParseResult schema. Use the same JobSpecV1 contract as voice intake.
Never infer or default dates, stairs, elevators, floors, parking, carry distance, inventory,
services, insurance, fees, or availability. Missing facts must remain null or empty and must be
listed in missing_fields. Add ambiguous facts to fields_requiring_confirmation and explain them
in warnings. Attach field-level document provenance where practical. Never mark the JobSpec as
confirmed or locked.
"""


def _normalize_document_result(
    response: DocumentParseResult | dict[str, Any],
) -> DocumentParseResult:
    """Make deterministic completeness metadata authoritative after fact validation."""

    payload = (
        response.model_dump(mode="python")
        if isinstance(response, DocumentParseResult)
        else deepcopy(response)
    )
    job_spec = JobSpecV1.model_validate(payload.get("job_spec"))
    payload["job_spec"] = job_spec.model_dump(mode="python")
    payload["missing_fields"] = job_spec.missing_required_fields()
    return DocumentParseResult.model_validate(payload)


class OpenAIDocumentParser:
    def __init__(
        self,
        client: StructuredDocumentClient,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._model = model or os.getenv("OPENAI_DOCUMENT_MODEL", "gpt-4.1-mini")

    def parse_document(
        self,
        content: bytes,
        mime_type: str,
        source_id: str,
    ) -> DocumentParseResult:
        if mime_type not in SUPPORTED_DOCUMENT_TYPES:
            raise ValueError(f"unsupported document type: {mime_type}")
        if not content:
            raise ValueError("document content must not be empty")
        if not source_id.strip():
            raise ValueError("source_id must not be empty")
        response = self._client.parse(
            model=self._model,
            system_prompt=DOCUMENT_SYSTEM_PROMPT,
            content=content,
            mime_type=mime_type,
            source_id=source_id,
            response_schema=DocumentParseResult,
        )
        result = _normalize_document_result(response)
        if result.job_spec.intake_source is not IntakeSource.DOCUMENT:
            raise ValueError("document parsing must produce intake_source=document")
        if result.job_spec.confirmed or result.job_spec.locked_version is not None:
            raise ValueError("document parsing cannot confirm or lock a JobSpec")
        return result
