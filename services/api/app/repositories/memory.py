"""Process-local mock repository; no Supabase instance is required."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import RLock
from typing import Any
from uuid import UUID

from services.api.app.contracts import (
    CallRecord,
    JobRecord,
    QuoteV1,
    VerificationStatus,
)
from services.api.app.core.errors import (
    DomainConflict,
    DuplicateResource,
    ResourceNotFound,
)
from services.api.app.orchestration.intake_sessions import (
    IntakeSession,
    validate_intake_session_update,
)
from services.api.app.orchestration.models import CallAttempt, JobEvent
from services.api.app.repositories.base import (
    VoiceIntakeCompletion,
    VoiceIntakeFinalizeRequest,
    VoiceIntakeMaterialization,
    VoiceWebhookClaimResult,
    VoiceWebhookFailure,
    VoiceWebhookFailureResult,
    VoiceWebhookFinalizeRequest,
    VoiceWebhookFinalizeResult,
    VoiceWebhookLease,
    VoiceWebhookMaterialization,
)


class InMemoryRepository:
    """Synchronized backing store implementing all orchestration repositories."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, dict[str, Any]] = {}
        self._attempts: dict[UUID, dict[str, Any]] = {}
        self._events: dict[UUID, list[dict[str, Any]]] = {}
        self._intake_sessions: dict[UUID, dict[str, Any]] = {}
        self._webhook_keys: set[str] = set()
        self._voice_webhook_receipts: dict[str, dict[str, Any]] = {}
        self._job_revisions: dict[UUID, int] = {}
        self._lock = RLock()

    def create(self, record: JobRecord) -> JobRecord:
        job_id = record.job_spec.job_id
        with self._lock:
            if job_id in self._jobs:
                raise DuplicateResource(f"Job {job_id} already exists")
            self._jobs[job_id] = deepcopy(record.model_dump(mode="json"))
            self._job_revisions[job_id] = 0
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
                    if (item.get("reference") or {}).get("conversation_id") == conversation_id
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
        """Compatibility path for legacy normalized events; new voice flows use leases."""

        with self._lock:
            if idempotency_key in self._webhook_keys:
                return False
            self._webhook_keys.add(idempotency_key)
            return True

    def claim_voice_webhook_receipt(
        self,
        lease: VoiceWebhookLease,
    ) -> VoiceWebhookClaimResult:
        candidate = VoiceWebhookLease.model_validate(lease.model_dump(mode="python"))
        with self._lock:
            current = self._voice_webhook_receipts.get(candidate.idempotency_key)
            if current is None:
                self._voice_webhook_receipts[candidate.idempotency_key] = {
                    "event_type": candidate.event_type,
                    "status": "processing",
                    "lease_token": candidate.lease_token,
                    "lease_expires_at": candidate.lease_expires_at,
                    "retryable": False,
                    "failure_code": None,
                    "attempt_count": 1,
                }
                return VoiceWebhookClaimResult(claimed=True, processed=False)
            if current["event_type"] != candidate.event_type:
                raise DomainConflict("Voice webhook receipt event type does not match")
            if current["status"] == "processed":
                return VoiceWebhookClaimResult(claimed=False, processed=True)
            if (
                current["status"] == "processing"
                and current["lease_token"] == candidate.lease_token
                and current["lease_expires_at"] > candidate.now
            ):
                return VoiceWebhookClaimResult(claimed=True, processed=False)
            if (
                current["status"] == "processing"
                and current["lease_expires_at"] > candidate.now
            ):
                return VoiceWebhookClaimResult(claimed=False, processed=False)
            if current["status"] == "failed" and not current["retryable"]:
                return VoiceWebhookClaimResult(claimed=False, processed=False)
            if current["attempt_count"] >= 100:
                raise DomainConflict("Voice webhook receipt retry limit was reached")
            current.update(
                {
                    "status": "processing",
                    "lease_token": candidate.lease_token,
                    "lease_expires_at": candidate.lease_expires_at,
                    "retryable": False,
                    "failure_code": None,
                    "attempt_count": current["attempt_count"] + 1,
                }
            )
            return VoiceWebhookClaimResult(claimed=True, processed=False)

    def fail_voice_webhook_receipt(
        self,
        idempotency_key: str,
        lease_token: UUID,
        failure_code: str,
        retryable: bool,
        now: datetime,
    ) -> VoiceWebhookFailureResult:
        request = VoiceWebhookFailure(
            idempotency_key=idempotency_key,
            lease_token=lease_token,
            failure_code=failure_code,
            retryable=retryable,
            now=now,
        )
        with self._lock:
            receipt = self._require_active_receipt(
                request.idempotency_key,
                request.lease_token,
                request.now,
            )
            receipt.update(
                {
                    "status": "failed",
                    "lease_token": None,
                    "lease_expires_at": None,
                    "retryable": request.retryable,
                    "failure_code": request.failure_code,
                }
            )
        return VoiceWebhookFailureResult(retryable=request.retryable)

    def finalize_voice_webhook(
        self,
        idempotency_key: str,
        lease_token: UUID,
        materialization: VoiceWebhookMaterialization,
        now: datetime,
    ) -> VoiceWebhookFinalizeResult:
        request = VoiceWebhookFinalizeRequest(
            idempotency_key=idempotency_key,
            lease_token=lease_token,
            materialization=materialization,
            now=now,
        )
        candidate = request.materialization
        with self._lock:
            receipt = self._voice_webhook_receipts.get(request.idempotency_key)
            if receipt is not None and receipt["status"] == "processed":
                return VoiceWebhookFinalizeResult(duplicate=True)
            receipt = self._require_active_receipt(
                request.idempotency_key,
                request.lease_token,
                request.now,
            )
            if receipt["event_type"] != candidate.event.event_type:
                raise DomainConflict("Voice webhook receipt event type does not match")
            if candidate.attempt.call_id not in self._attempts:
                raise ResourceNotFound(
                    f"Call attempt {candidate.attempt.call_id} was not found"
                )
            current_payload = self._require_job(candidate.job.job_spec.job_id)
            current = JobRecord.model_validate(deepcopy(current_payload))
            if self._job_revisions[candidate.job.job_spec.job_id] != candidate.expected_revision:
                raise DomainConflict("Voice aggregate revision conflict")
            if current.job_spec.confirmed and (
                current.job_spec.model_dump(mode="json")
                != candidate.job.job_spec.model_dump(mode="json")
            ):
                raise DomainConflict("Confirmed JobSpec version is locked and cannot be changed")
            if not {item.call_id for item in current.calls}.issubset(
                {item.call_id for item in candidate.job.calls}
            ) or not {item.quote_id for item in current.quotes}.issubset(
                {item.quote_id for item in candidate.job.quotes}
            ):
                raise DomainConflict("Voice materialization cannot discard canonical results")

            attempt_payload = deepcopy(candidate.attempt.model_dump(mode="json"))
            job_payload = deepcopy(candidate.job.model_dump(mode="json"))
            event_payload = deepcopy(candidate.event.model_dump(mode="json"))
            event_payloads = deepcopy(self._events.get(candidate.event.job_id, []))
            if not any(
                item["event_id"] == str(candidate.event.event_id)
                for item in event_payloads
            ):
                event_payloads.append(event_payload)
            processed_receipt = {
                **deepcopy(receipt),
                "status": "processed",
                "lease_token": None,
                "lease_expires_at": None,
                "retryable": False,
                "failure_code": None,
            }

            self._attempts[candidate.attempt.call_id] = attempt_payload
            self._jobs[candidate.job.job_spec.job_id] = job_payload
            self._events[candidate.event.job_id] = event_payloads
            self._job_revisions[candidate.job.job_spec.job_id] += 1
            self._voice_webhook_receipts[request.idempotency_key] = processed_receipt
        return VoiceWebhookFinalizeResult(duplicate=False)

    def finalize_voice_intake_webhook(
        self,
        idempotency_key: str,
        lease_token: UUID,
        materialization: VoiceIntakeMaterialization,
        now: datetime,
    ) -> VoiceWebhookFinalizeResult:
        request = VoiceIntakeFinalizeRequest(
            idempotency_key=idempotency_key,
            lease_token=lease_token,
            materialization=materialization,
            now=now,
        )
        candidate = request.materialization
        event_type = (
            candidate.event.event_type
            if isinstance(candidate, VoiceIntakeCompletion)
            else candidate.event_type
        )
        with self._lock:
            receipt = self._voice_webhook_receipts.get(request.idempotency_key)
            if receipt is not None and receipt["status"] == "processed":
                return VoiceWebhookFinalizeResult(duplicate=True)
            receipt = self._require_active_receipt(
                request.idempotency_key,
                request.lease_token,
                request.now,
            )
            if receipt["event_type"] != event_type:
                raise DomainConflict("Voice webhook receipt event type does not match")

            current_payload = self._intake_sessions.get(candidate.session.intake_session_id)
            if current_payload is None:
                raise ResourceNotFound(
                    f"Intake session {candidate.session.intake_session_id} was not found"
                )
            current_session = IntakeSession.model_validate(deepcopy(current_payload))
            validate_intake_session_update(current_session, candidate.session)

            session_payload = deepcopy(candidate.session.model_dump(mode="json"))
            processed_receipt = {
                **deepcopy(receipt),
                "status": "processed",
                "lease_token": None,
                "lease_expires_at": None,
                "retryable": False,
                "failure_code": None,
            }

            if isinstance(candidate, VoiceIntakeCompletion):
                existing_payload = self._jobs.get(candidate.session.job_id)
                if existing_payload is not None:
                    existing = JobRecord.model_validate(deepcopy(existing_payload))
                    if existing != candidate.job:
                        raise DomainConflict(
                            "Intake session owns a different canonical job"
                        )
                event_payloads = deepcopy(self._events.get(candidate.session.job_id, []))
                event_payload = deepcopy(candidate.event.model_dump(mode="json"))
                matching_event = next(
                    (
                        item
                        for item in event_payloads
                        if item["event_id"] == str(candidate.event.event_id)
                    ),
                    None,
                )
                if matching_event is not None and matching_event != event_payload:
                    raise DomainConflict("Voice intake event identity conflict")
                if matching_event is None:
                    event_payloads.append(event_payload)
                job_payload = deepcopy(candidate.job.model_dump(mode="json"))

                self._jobs[candidate.session.job_id] = job_payload
                self._job_revisions.setdefault(candidate.session.job_id, 0)
                self._events[candidate.session.job_id] = event_payloads
            elif candidate.session.job_id in self._jobs:
                raise DomainConflict("Failed intake session cannot own a canonical job")

            self._intake_sessions[candidate.session.intake_session_id] = session_payload
            self._voice_webhook_receipts[request.idempotency_key] = processed_receipt
        return VoiceWebhookFinalizeResult(duplicate=False)

    def get_job_revision(self, job_id: UUID) -> int:
        with self._lock:
            self._require_job(job_id)
            return self._job_revisions[job_id]

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
            record.quotes = [item for item in record.quotes if item.quote_id != quote.quote_id]
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
            and not quote.manually_fabricated
            and (quote.comparable_total is not None or quote.negotiated_total is not None)
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

    def create_intake_session(self, session: IntakeSession) -> IntakeSession:
        candidate = self._copy_intake_session(session)
        with self._lock:
            if candidate.provider_call_key_hash is not None:
                replay = next(
                    (
                        IntakeSession.model_validate(deepcopy(payload))
                        for payload in self._intake_sessions.values()
                        if payload.get("provider_call_key_hash") == candidate.provider_call_key_hash
                    ),
                    None,
                )
                if replay is not None:
                    return replay
            if candidate.intake_session_id in self._intake_sessions:
                raise DuplicateResource(
                    f"Intake session {candidate.intake_session_id} already exists"
                )
            if any(
                payload["job_id"] == str(candidate.job_id)
                for payload in self._intake_sessions.values()
            ):
                raise DuplicateResource(
                    f"An intake session already exists for job {candidate.job_id}"
                )
            if candidate.job_id in self._jobs:
                raise DomainConflict("Intake session must exist before its canonical JobRecord")
            self._intake_sessions[candidate.intake_session_id] = deepcopy(
                candidate.model_dump(mode="json")
            )
        return self._copy_intake_session(candidate)

    def get_intake_session(self, session_id: UUID) -> IntakeSession | None:
        with self._lock:
            payload = deepcopy(self._intake_sessions.get(session_id))
        return IntakeSession.model_validate(payload) if payload is not None else None

    def find_intake_session_by_provider_call_key_hash(
        self,
        provider_call_key_hash: str,
    ) -> IntakeSession | None:
        with self._lock:
            payload = next(
                (
                    deepcopy(item)
                    for item in self._intake_sessions.values()
                    if item.get("provider_call_key_hash") == provider_call_key_hash
                ),
                None,
            )
        return IntakeSession.model_validate(payload) if payload is not None else None

    def find_intake_session_by_conversation_id(
        self,
        conversation_id: str,
    ) -> IntakeSession | None:
        with self._lock:
            payload = next(
                (
                    deepcopy(item)
                    for item in self._intake_sessions.values()
                    if item.get("conversation_id") == conversation_id
                ),
                None,
            )
        return IntakeSession.model_validate(payload) if payload is not None else None

    def save_intake_session(self, session: IntakeSession) -> IntakeSession:
        candidate = self._copy_intake_session(session)
        with self._lock:
            payload = self._intake_sessions.get(candidate.intake_session_id)
            if payload is None:
                raise ResourceNotFound(
                    f"Intake session {candidate.intake_session_id} was not found"
                )
            current = IntakeSession.model_validate(deepcopy(payload))
            validate_intake_session_update(current, candidate)
            if candidate.conversation_id is not None and any(
                item.get("conversation_id") == candidate.conversation_id
                and session_id != candidate.intake_session_id
                for session_id, item in self._intake_sessions.items()
            ):
                raise DuplicateResource("An intake session already owns this conversation")
            self._intake_sessions[candidate.intake_session_id] = deepcopy(
                candidate.model_dump(mode="json")
            )
        return self._copy_intake_session(candidate)

    def reset(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._attempts.clear()
            self._events.clear()
            self._intake_sessions.clear()
            self._webhook_keys.clear()
            self._voice_webhook_receipts.clear()
            self._job_revisions.clear()

    def _require_job(self, job_id: UUID) -> dict[str, Any]:
        payload = self._jobs.get(job_id)
        if payload is None:
            raise ResourceNotFound(f"Job {job_id} was not found")
        return payload

    def _require_active_receipt(
        self,
        idempotency_key: str,
        lease_token: UUID,
        now: datetime,
    ) -> dict[str, Any]:
        receipt = self._voice_webhook_receipts.get(idempotency_key)
        if (
            receipt is None
            or receipt["status"] != "processing"
            or receipt["lease_token"] != lease_token
            or receipt["lease_expires_at"] <= now
        ):
            raise DomainConflict("Voice webhook receipt lease mismatch or expired")
        return receipt

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

    @staticmethod
    def _copy_intake_session(session: IntakeSession) -> IntakeSession:
        return IntakeSession.model_validate(deepcopy(session.model_dump(mode="json")))
