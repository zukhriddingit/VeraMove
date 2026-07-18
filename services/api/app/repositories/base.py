"""Persistence protocol consumed by orchestration."""

from typing import Any, Protocol
from uuid import UUID

from services.api.app.contracts import JobRecord


class JobRepository(Protocol):
    def create(self, record: JobRecord) -> JobRecord: ...

    def get(self, job_id: UUID) -> JobRecord | None: ...

    def save(self, record: JobRecord) -> JobRecord: ...

    def record_webhook(self, idempotency_key: str, payload: dict[str, Any]) -> bool: ...

    def reset(self) -> None: ...
