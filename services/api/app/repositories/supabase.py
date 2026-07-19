"""Supabase-backed repository preserving VeraMove's canonical aggregates."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from services.api.app.contracts import (
    CallRecord,
    DataClassification,
    JobRecord,
    QuoteV1,
    RecommendationV1,
    TranscriptEvidence,
    Vendor,
    VerificationStatus,
)
from services.api.app.core.errors import (
    DomainConflict,
    DuplicateResource,
    ResourceNotFound,
)
from services.api.app.orchestration.models import CallAttempt, JobEvent
from services.api.app.repositories.supabase_client import (
    SupabaseDuplicate,
    SupabaseTableClient,
)

_SENSITIVE_EVENT_KEYS = frozenset(
    {
        "analysis",
        "from_number",
        "phone",
        "phone_number",
        "raw_body",
        "raw_payload",
        "to_number",
        "transcript",
    }
)
_PHONE_LIKE = re.compile(r"\+?\d[\d\s().-]{6,}\d")


class SupabaseRepository:
    """One fail-closed persistent implementation of all repository protocols."""

    def __init__(self, client: SupabaseTableClient) -> None:
        self._client = client

    def create(self, record: JobRecord) -> JobRecord:
        candidate = self._copy_job(record)
        try:
            self._client.insert("jobs", self._job_row(candidate))
        except SupabaseDuplicate as exc:
            raise DuplicateResource(
                f"Job {candidate.job_spec.job_id} already exists"
            ) from exc
        if candidate.recommendation is not None:
            self._persist_recommendation(candidate)
        return self._copy_job(candidate)

    def get(self, job_id: UUID) -> JobRecord | None:
        rows = self._client.select_many("jobs", {"id": f"eq.{job_id}"})
        if not rows:
            return None
        return JobRecord.model_validate(deepcopy(rows[0]["payload"]))

    def save(self, record: JobRecord) -> JobRecord:
        candidate = self._copy_job(record)
        current = self.get(candidate.job_spec.job_id)
        if current is None:
            raise ResourceNotFound(
                f"Job {candidate.job_spec.job_id} was not found"
            )
        if current.job_spec.confirmed and (
            current.job_spec.model_dump(mode="json")
            != candidate.job_spec.model_dump(mode="json")
        ):
            raise DomainConflict(
                "Confirmed JobSpec version is locked and cannot be changed"
            )
        self._client.upsert(
            "jobs",
            self._job_row(candidate),
            on_conflict="id",
        )
        self._persist_recommendation(candidate)
        return self._copy_job(candidate)

    def create_attempt(self, attempt: CallAttempt) -> CallAttempt:
        candidate = self._copy_attempt(attempt)
        self._require_job(candidate.job_id)
        self._persist_vendor(candidate.vendor)
        try:
            self._client.insert("call_attempts", self._attempt_row(candidate))
        except SupabaseDuplicate as exc:
            raise DuplicateResource(
                f"Call attempt {candidate.call_id} already exists"
            ) from exc
        return self._copy_attempt(candidate)

    def save_attempt(self, attempt: CallAttempt) -> CallAttempt:
        candidate = self._copy_attempt(attempt)
        if self.get_attempt(candidate.call_id) is None:
            raise ResourceNotFound(
                f"Call attempt {candidate.call_id} was not found"
            )
        self._persist_vendor(candidate.vendor)
        self._client.upsert(
            "call_attempts",
            self._attempt_row(candidate),
            on_conflict="id",
        )
        return self._copy_attempt(candidate)

    def get_attempt(self, call_id: UUID) -> CallAttempt | None:
        rows = self._client.select_many(
            "call_attempts",
            {"id": f"eq.{call_id}"},
        )
        if not rows:
            return None
        return CallAttempt.model_validate(deepcopy(rows[0]["payload"]))

    def list_attempts(self, job_id: UUID) -> list[CallAttempt]:
        rows = self._client.select_many(
            "call_attempts",
            {"job_id": f"eq.{job_id}"},
        )
        return [
            CallAttempt.model_validate(deepcopy(row["payload"]))
            for row in rows
        ]

    def find_attempt_by_conversation_id(
        self,
        conversation_id: str,
    ) -> CallAttempt | None:
        rows = self._client.select_many(
            "call_attempts",
            {"conversation_id": f"eq.{conversation_id}"},
        )
        if not rows:
            return None
        return CallAttempt.model_validate(deepcopy(rows[0]["payload"]))

    def save_call(self, call: CallRecord) -> CallRecord:
        candidate = self._copy_call(call)
        record = self._require_job(candidate.job_id)
        attempt = self.get_attempt(candidate.call_id)
        external_call_id = (
            attempt.reference.provider_call_id
            if attempt is not None and attempt.reference is not None
            else self._existing_external_call_id(candidate.call_id)
        )
        self._persist_vendor(candidate.vendor)
        self._client.upsert(
            "calls",
            self._call_row(candidate, external_call_id),
            on_conflict="id",
        )
        record.calls = [
            item for item in record.calls if item.call_id != candidate.call_id
        ]
        record.calls.append(candidate)
        self.save(record)
        return self._copy_call(candidate)

    def list_calls(self, job_id: UUID) -> list[CallRecord]:
        rows = self._client.select_many(
            "calls",
            {
                "job_id": f"eq.{job_id}",
                "record_type": "eq.canonical",
            },
        )
        return [
            CallRecord.model_validate(deepcopy(row["payload"]))
            for row in rows
        ]

    def reserve_webhook(self, idempotency_key: str) -> bool:
        webhook_id = uuid5(NAMESPACE_URL, f"webhook:{idempotency_key}")
        try:
            self._client.insert(
                "event_log",
                {
                    "id": str(webhook_id),
                    "job_id": None,
                    "source": "elevenlabs",
                    "event_type": "reserved",
                    "idempotency_key": idempotency_key,
                    "data_classification": DataClassification.SYNTHETIC.value,
                    "payload": {},
                },
            )
        except SupabaseDuplicate:
            return False
        return True

    def append_event(self, event: JobEvent) -> JobEvent:
        self._require_job(event.job_id)
        safe_event = self._safe_event(event)
        try:
            self._client.insert(
                "event_log",
                {
                    "id": str(safe_event.event_id),
                    "job_id": str(safe_event.job_id),
                    "source": "veramove",
                    "event_type": safe_event.event_type,
                    "idempotency_key": f"job-event:{safe_event.event_id}",
                    "data_classification": self._job_classification(
                        safe_event.job_id
                    ),
                    "payload": safe_event.model_dump(mode="json"),
                    "created_at": safe_event.occurred_at.isoformat(),
                },
            )
        except SupabaseDuplicate as exc:
            raise DuplicateResource(
                f"Job event {safe_event.event_id} already exists"
            ) from exc
        return self._copy_event(safe_event)

    def list_events(self, job_id: UUID) -> list[JobEvent]:
        rows = self._client.select_many(
            "event_log",
            {
                "job_id": f"eq.{job_id}",
                "source": "eq.veramove",
            },
        )
        return [
            JobEvent.model_validate(deepcopy(row["payload"]))
            for row in rows
        ]

    def save_quote(self, quote: QuoteV1) -> QuoteV1:
        candidate = self._copy_quote(quote)
        record = self._require_job(candidate.job_id)
        self._persist_vendor(candidate.vendor)
        self._client.upsert(
            "quotes",
            self._quote_row(candidate),
            on_conflict="id",
        )
        for evidence in candidate.transcript_evidence:
            self._client.upsert(
                "transcript_evidence",
                self._evidence_row(candidate, evidence),
                on_conflict="id",
            )
        record.quotes = [
            item for item in record.quotes if item.quote_id != candidate.quote_id
        ]
        record.quotes.append(candidate)
        self.save(record)
        return self._copy_quote(candidate)

    def list_quotes(self, job_id: UUID) -> list[QuoteV1]:
        rows = self._client.select_many(
            "quotes",
            {"job_id": f"eq.{job_id}"},
        )
        return [
            QuoteV1.model_validate(deepcopy(row["payload"]))
            for row in rows
        ]

    def get_verified_competing_quote(
        self,
        job_id: UUID,
        target_vendor_id: UUID,
        job_spec_version: str,
    ) -> QuoteV1 | None:
        eligible = [
            quote
            for quote in self.list_quotes(job_id)
            if quote.vendor.vendor_id != target_vendor_id
            and quote.job_spec_version == job_spec_version
            and quote.verification_status is VerificationStatus.VERIFIED
            and quote.verified_data
            and quote.transcript_evidence
            and not quote.manually_fabricated
            and (
                quote.comparable_total is not None
                or quote.negotiated_total is not None
            )
        ]
        selected = min(
            eligible,
            key=lambda quote: (
                quote.comparable_total
                if quote.comparable_total is not None
                else quote.negotiated_total
            ),
            default=None,
        )
        return self._copy_quote(selected) if selected is not None else None

    def reset(self) -> None:
        raise RuntimeError("SupabaseRepository reset is disabled")

    def _require_job(self, job_id: UUID) -> JobRecord:
        record = self.get(job_id)
        if record is None:
            raise ResourceNotFound(f"Job {job_id} was not found")
        return record

    def _job_classification(self, job_id: UUID) -> str:
        return self._require_job(job_id).job_spec.data_classification.value

    def _existing_external_call_id(self, call_id: UUID) -> str | None:
        rows = self._client.select_many(
            "calls",
            {"id": f"eq.{call_id}"},
        )
        if not rows:
            return None
        external_call_id = rows[0].get("external_call_id")
        return external_call_id if isinstance(external_call_id, str) else None

    def _persist_vendor(self, vendor: Vendor) -> None:
        self._client.upsert(
            "vendors",
            {
                "id": str(vendor.vendor_id),
                "slug": vendor.slug,
                "data_classification": vendor.data_classification.value,
                "provenance": [
                    item.model_dump(mode="json") for item in vendor.provenance
                ],
                "payload": vendor.model_dump(mode="json"),
            },
            on_conflict="id",
        )

    def _persist_recommendation(self, record: JobRecord) -> None:
        recommendation = record.recommendation
        if recommendation is None:
            return
        self._client.upsert(
            "recommendations",
            self._recommendation_row(
                recommendation,
                record.job_spec.data_classification,
            ),
            on_conflict="id",
        )

    @staticmethod
    def _job_row(record: JobRecord) -> dict[str, Any]:
        job_spec = record.job_spec
        return {
            "id": str(job_spec.job_id),
            "job_spec_version": job_spec.version,
            "state": record.state.value,
            "confirmed_at": (
                job_spec.confirmed_at.isoformat()
                if job_spec.confirmed_at is not None
                else None
            ),
            "locked_job_spec_version": job_spec.locked_version,
            "data_classification": job_spec.data_classification.value,
            "payload": record.model_dump(mode="json"),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    @staticmethod
    def _attempt_row(attempt: CallAttempt) -> dict[str, Any]:
        return {
            "id": str(attempt.call_id),
            "job_id": str(attempt.job_id),
            "vendor_id": str(attempt.vendor.vendor_id),
            "conversation_id": (
                attempt.reference.conversation_id
                if attempt.reference is not None
                else None
            ),
            "external_call_id": (
                attempt.reference.provider_call_id
                if attempt.reference is not None
                else None
            ),
            "idempotency_key": f"call:{attempt.call_id}",
            "status": attempt.status.value,
            "data_classification": attempt.vendor.data_classification.value,
            "payload": attempt.model_dump(mode="json"),
            "created_at": attempt.started_at.isoformat(),
            "updated_at": (
                attempt.completed_at or attempt.started_at
            ).isoformat(),
        }

    @staticmethod
    def _call_row(
        call: CallRecord,
        external_call_id: str | None,
    ) -> dict[str, Any]:
        return {
            "id": str(call.call_id),
            "job_id": str(call.job_id),
            "vendor_id": str(call.vendor.vendor_id),
            "external_call_id": external_call_id,
            "idempotency_key": f"call:{call.call_id}",
            "status": call.status.value,
            "outcome_type": call.outcome.type.value,
            "record_type": "canonical",
            "data_classification": call.vendor.data_classification.value,
            "payload": call.model_dump(mode="json"),
            "created_at": call.started_at.isoformat(),
            "updated_at": (call.completed_at or call.started_at).isoformat(),
        }

    @staticmethod
    def _quote_row(quote: QuoteV1) -> dict[str, Any]:
        call_id = (
            quote.transcript_evidence[0].call_id
            if quote.transcript_evidence
            else None
        )
        return {
            "id": str(quote.quote_id),
            "job_id": str(quote.job_id),
            "vendor_id": str(quote.vendor.vendor_id),
            "call_id": str(call_id) if call_id is not None else None,
            "quote_version": "1.0",
            "job_spec_version": quote.job_spec_version,
            "verification_status": quote.verification_status.value,
            "provisional_payload": deepcopy(quote.provisional_data),
            "verified_payload": deepcopy(quote.verified_data),
            "provenance": [
                item.model_dump(mode="json") for item in quote.provenance
            ],
            "manually_fabricated": quote.manually_fabricated,
            "data_classification": quote.data_classification.value,
            "payload": quote.model_dump(mode="json"),
        }

    @staticmethod
    def _evidence_row(
        quote: QuoteV1,
        evidence: TranscriptEvidence,
    ) -> dict[str, Any]:
        return {
            "id": str(evidence.evidence_id),
            "job_id": str(quote.job_id),
            "call_id": str(evidence.call_id),
            "verification_status": quote.verification_status.value,
            "recording_url": str(evidence.recording_url),
            "data_classification": evidence.data_classification.value,
            "payload": evidence.model_dump(mode="json"),
        }

    @staticmethod
    def _recommendation_row(
        recommendation: RecommendationV1,
        data_classification: DataClassification,
    ) -> dict[str, Any]:
        provenance = [
            {
                "evidence_id": str(evidence.evidence_id),
                "call_id": str(evidence.call_id),
                "recording_url": str(evidence.recording_url),
            }
            for evidence in recommendation.transcript_evidence
        ]
        return {
            "id": str(recommendation.recommendation_id),
            "job_id": str(recommendation.job_id),
            "recommendation_version": recommendation.version,
            "data_classification": data_classification.value,
            "provenance": provenance,
            "payload": recommendation.model_dump(mode="json"),
            "created_at": recommendation.generated_at.isoformat(),
            "updated_at": recommendation.generated_at.isoformat(),
        }

    @staticmethod
    def _safe_event(event: JobEvent) -> JobEvent:
        metadata = {
            key: value
            for key, value in event.metadata.items()
            if key.lower() not in _SENSITIVE_EVENT_KEYS
            and not (
                isinstance(value, str)
                and _PHONE_LIKE.search(value) is not None
            )
        }
        return event.model_copy(update={"metadata": metadata}, deep=True)

    @staticmethod
    def _copy_job(record: JobRecord) -> JobRecord:
        return JobRecord.model_validate(deepcopy(record.model_dump(mode="json")))

    @staticmethod
    def _copy_attempt(attempt: CallAttempt) -> CallAttempt:
        return CallAttempt.model_validate(deepcopy(attempt.model_dump(mode="json")))

    @staticmethod
    def _copy_call(call: CallRecord) -> CallRecord:
        return CallRecord.model_validate(deepcopy(call.model_dump(mode="json")))

    @staticmethod
    def _copy_event(event: JobEvent) -> JobEvent:
        return JobEvent.model_validate(deepcopy(event.model_dump(mode="json")))

    @staticmethod
    def _copy_quote(quote: QuoteV1) -> QuoteV1:
        return QuoteV1.model_validate(deepcopy(quote.model_dump(mode="json")))


__all__ = ["SupabaseRepository"]
