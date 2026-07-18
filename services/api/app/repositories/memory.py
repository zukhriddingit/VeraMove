"""Process-local mock repository; no Supabase instance is required."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any
from uuid import UUID

from services.api.app.contracts import JobRecord
from services.api.app.core.errors import DomainConflict, DuplicateResource, ResourceNotFound


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[UUID, dict[str, Any]] = {}
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
        candidate = self._copy(record)
        with self._lock:
            if job_id not in self._jobs:
                raise ResourceNotFound(f"Job {job_id} was not found")
            current = JobRecord.model_validate(self._jobs[job_id])
            if current.job_spec.confirmed and candidate.job_spec.model_dump(
                mode="json"
            ) != current.job_spec.model_dump(mode="json"):
                raise DomainConflict("Confirmed JobSpec version is locked and cannot be changed")
            self._jobs[job_id] = deepcopy(candidate.model_dump(mode="json"))
        return self._copy(candidate)

    def record_webhook(self, idempotency_key: str, payload: dict[str, Any]) -> bool:
        del payload
        with self._lock:
            if idempotency_key in self._webhook_keys:
                return False
            self._webhook_keys.add(idempotency_key)
            return True

    def reset(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._webhook_keys.clear()

    @staticmethod
    def _copy(record: JobRecord) -> JobRecord:
        return JobRecord.model_validate(deepcopy(record.model_dump(mode="json")))
