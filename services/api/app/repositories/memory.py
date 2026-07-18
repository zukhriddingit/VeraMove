"""Process-local mock repository; no Supabase instance is required."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any
from uuid import UUID

from services.api.app.contracts import (
    CallRecord,
    JobRecord,
    QuoteV1,
    VerificationStatus,
)
from services.api.app.core.errors import DuplicateResource, ResourceNotFound
from services.api.app.orchestration.models import CallAttempt, JobEvent


class InMemoryRepository:
    """Synchronized backing store implementing all orchestration repositories."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, dict[str, Any]] = {}
        self._attempts: dict[UUID, dict[str, Any]] = {}
        self._events: dict[UUID, list[dict[str, Any]]] = {}
        self._webhook_keys: set[str] = set()
        self._lock = RLock()

    def create(self, record: JobRecord) -> JobRecord:
        job_id = record.job_spec.job_id
        with self._lock:
            if job_id in self._jobs:
                raise DuplicateResource(f"Job {job_id} already exists")
            self._jobs[job_id] = deepcopy(record.model_dump(mode="json"))
        return self._copy(record)

    def get(self, job_id: UUID) -> JobRecord | None:
        with self._lock:
            payload = deepcopy(self._jobs.get(job_id))
        return JobRecord.model_validate(payload) if payload is not None else None

    def save(self, record: JobRecord) -> JobRecord:
        job_id = record.job_spec.job_id
        with self._lock:
            if job_id not in self._jobs:
                raise ResourceNotFound(f"Job {job_id} was not found")
            self._jobs[job_id] = deepcopy(record.model_dump(mode="json"))
        return self._copy(record)

    def create_attempt(self, attempt: CallAttempt) -> CallAttempt:
        with self._lock:
            self._require_job(attempt.job_id)
            if attempt.call_id in self._attempts:
                raise DuplicateResource(f"Call attempt {attempt.call_id} already exists")
            self._attempts[attempt.call_id] = deepcopy(attempt.model_dump(mode="json"))
        return self._copy_attempt(attempt)

    def save_attempt(self, attempt: CallAttempt) -> CallAttempt:
        with self._lock:
            if attempt.call_id not in self._attempts:
                raise ResourceNotFound(f"Call attempt {attempt.call_id} was not found")
            self._attempts[attempt.call_id] = deepcopy(attempt.model_dump(mode="json"))
        return self._copy_attempt(attempt)

    def get_attempt(self, call_id: UUID) -> CallAttempt | None:
        with self._lock:
            payload = deepcopy(self._attempts.get(call_id))
        return CallAttempt.model_validate(payload) if payload is not None else None

    def list_attempts(self, job_id: UUID) -> list[CallAttempt]:
        with self._lock:
            payloads = [
                deepcopy(payload)
                for payload in self._attempts.values()
                if payload["job_id"] == str(job_id)
            ]
        return [CallAttempt.model_validate(payload) for payload in payloads]

    def find_attempt_by_conversation_id(
        self,
        conversation_id: str,
    ) -> CallAttempt | None:
        with self._lock:
            payload = next(
                (
                    deepcopy(item)
                    for item in self._attempts.values()
                    if (item.get("reference") or {}).get("conversation_id")
                    == conversation_id
                ),
                None,
            )
        return CallAttempt.model_validate(payload) if payload is not None else None

    def save_call(self, call: CallRecord) -> CallRecord:
        with self._lock:
            payload = self._require_job(call.job_id)
            record = JobRecord.model_validate(deepcopy(payload))
            record.calls = [item for item in record.calls if item.call_id != call.call_id]
            record.calls.append(call)
            self._jobs[call.job_id] = deepcopy(record.model_dump(mode="json"))
        return self._copy_call(call)

    def list_calls(self, job_id: UUID) -> list[CallRecord]:
        with self._lock:
            payload = deepcopy(self._jobs.get(job_id))
        if payload is None:
            return []
        return JobRecord.model_validate(payload).calls

    def reserve_webhook(self, idempotency_key: str) -> bool:
        with self._lock:
            if idempotency_key in self._webhook_keys:
                return False
            self._webhook_keys.add(idempotency_key)
            return True

    def record_webhook(self, idempotency_key: str, payload: dict[str, Any]) -> bool:
        """Temporary compatibility shim for the pre-migration service."""

        del payload
        return self.reserve_webhook(idempotency_key)

    def append_event(self, event: JobEvent) -> JobEvent:
        with self._lock:
            self._require_job(event.job_id)
            self._events.setdefault(event.job_id, []).append(
                deepcopy(event.model_dump(mode="json")),
            )
        return self._copy_event(event)

    def list_events(self, job_id: UUID) -> list[JobEvent]:
        with self._lock:
            payloads = deepcopy(self._events.get(job_id, []))
        return [JobEvent.model_validate(payload) for payload in payloads]

    def save_quote(self, quote: QuoteV1) -> QuoteV1:
        with self._lock:
            payload = self._require_job(quote.job_id)
            record = JobRecord.model_validate(deepcopy(payload))
            record.quotes = [
                item for item in record.quotes if item.quote_id != quote.quote_id
            ]
            record.quotes.append(quote)
            self._jobs[quote.job_id] = deepcopy(record.model_dump(mode="json"))
        return self._copy_quote(quote)

    def list_quotes(self, job_id: UUID) -> list[QuoteV1]:
        with self._lock:
            payload = deepcopy(self._jobs.get(job_id))
        if payload is None:
            return []
        return JobRecord.model_validate(payload).quotes

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
        ]
        selected = min(eligible, key=lambda quote: quote.negotiated_total, default=None)
        return self._copy_quote(selected) if selected is not None else None

    def reset(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._attempts.clear()
            self._events.clear()
            self._webhook_keys.clear()

    def _require_job(self, job_id: UUID) -> dict[str, Any]:
        payload = self._jobs.get(job_id)
        if payload is None:
            raise ResourceNotFound(f"Job {job_id} was not found")
        return payload

    @staticmethod
    def _copy(record: JobRecord) -> JobRecord:
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


# Temporary compatibility alias until orchestration service composition migrates.
InMemoryJobRepository = InMemoryRepository
