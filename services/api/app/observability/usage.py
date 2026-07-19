"""Bounded OpenAI usage telemetry that never retains prompts or responses."""

from __future__ import annotations

from collections import deque
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UsageRecord(BaseModel):
    """One safe provider-call measurement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: Literal["document_extraction", "recommendation_narration"]
    model: str = Field(min_length=1, max_length=200)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(ge=0)
    success_category: Literal["success", "provider_error", "invalid_response"]
    provider_request_id: str | None = Field(default=None, max_length=200)


class UsageAggregate(BaseModel):
    """Safe grouped usage returned by the integration-status API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: Literal["document_extraction", "recommendation_narration"]
    model: str
    request_count: int = Field(ge=0)
    successful_requests: int = Field(ge=0)
    failed_requests: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    total_latency_ms: int = Field(ge=0)


class UsageRecorder:
    """Thread-safe bounded recorder; telemetry can never break provider work."""

    def __init__(self, max_records: int = 1_000) -> None:
        if max_records < 1 or max_records > 10_000:
            raise ValueError("max_records must be between 1 and 10000")
        self._records: deque[UsageRecord] = deque(maxlen=max_records)
        self._lock = RLock()

    def record(self, record: UsageRecord) -> None:
        with self._lock:
            self._records.append(record.model_copy(deep=True))

    def snapshot(self) -> tuple[UsageRecord, ...]:
        with self._lock:
            return tuple(record.model_copy(deep=True) for record in self._records)

    def aggregates(self) -> tuple[UsageAggregate, ...]:
        grouped: dict[tuple[str, str], dict[str, int]] = {}
        for record in self.snapshot():
            key = (record.capability, record.model)
            values = grouped.setdefault(
                key,
                {
                    "request_count": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "total_latency_ms": 0,
                },
            )
            values["request_count"] += 1
            outcome_key = (
                "successful_requests" if record.success_category == "success" else "failed_requests"
            )
            values[outcome_key] += 1
            values["input_tokens"] += record.input_tokens
            values["output_tokens"] += record.output_tokens
            values["total_tokens"] += record.total_tokens
            values["total_latency_ms"] += record.latency_ms
        return tuple(
            UsageAggregate(capability=capability, model=model, **values)
            for (capability, model), values in sorted(grouped.items())
        )
