"""Supabase-backed repository preserving VeraMove's canonical aggregates."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from services.api.app.contracts import (
    CallRecord,
    DataClassification,
    JobRecord,
    JobState,
    JobVendorResearchV1,
    QuoteV1,
    RecommendationV1,
    TranscriptEvidence,
    Vendor,
    VendorCallAuthorizationV1,
    VendorSuppressionV1,
    VerificationStatus,
)
from services.api.app.core.errors import (
    DomainConflict,
    DuplicateResource,
    ProviderRequestError,
    ResourceNotFound,
)
from services.api.app.orchestration.intake_sessions import (
    IntakeRecoveryAction,
    IntakeSession,
    IntakeSessionStatus,
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
            raise DuplicateResource(f"Job {candidate.job_spec.job_id} already exists") from exc
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
            raise ResourceNotFound(f"Job {candidate.job_spec.job_id} was not found")
        if current.job_spec.confirmed and (
            current.job_spec.model_dump(mode="json") != candidate.job_spec.model_dump(mode="json")
        ):
            raise DomainConflict("Confirmed JobSpec version is locked and cannot be changed")
        self._client.upsert(
            "jobs",
            self._job_row(candidate),
            on_conflict="id",
        )
        self._persist_recommendation(candidate)
        return self._copy_job(candidate)

    def get_vendor_research(
        self,
        job_id: UUID,
        job_spec_version: str,
    ) -> JobVendorResearchV1 | None:
        rows = self._client.select_many(
            "vendor_research",
            {
                "job_id": f"eq.{job_id}",
                "job_spec_version": f"eq.{job_spec_version}",
            },
        )
        if not rows:
            return None
        if len(rows) != 1 or not isinstance(rows[0].get("payload"), dict):
            raise ProviderRequestError(
                "Supabase returned invalid vendor research"
            )
        return JobVendorResearchV1.model_validate(deepcopy(rows[0]["payload"]))

    def save_vendor_research(
        self,
        research: JobVendorResearchV1,
    ) -> JobVendorResearchV1:
        candidate = self._copy_vendor_research(research)
        job = self._require_job(candidate.job_id)
        if candidate.job_spec_version != job.job_spec.version:
            raise DomainConflict(
                "Vendor research JobSpec version does not match the job"
            )
        row_id = uuid5(
            NAMESPACE_URL,
            f"veramove-vendor-research:{candidate.job_id}:{candidate.job_spec_version}",
        )
        self._client.upsert(
            "vendor_research",
            {
                "id": str(row_id),
                "job_id": str(candidate.job_id),
                "job_spec_version": candidate.job_spec_version,
                "data_classification": (
                    DataClassification.REAL_REDACTED.value
                    if candidate.source == "tavily"
                    else DataClassification.SYNTHETIC.value
                ),
                "payload": candidate.model_dump(mode="json"),
                "created_at": candidate.created_at.isoformat(),
                "updated_at": candidate.updated_at.isoformat(),
            },
            on_conflict="id",
        )
        return self._copy_vendor_research(candidate)

    def get_vendor_call_authorization(
        self,
        job_id: UUID,
        job_spec_version: str,
        vendor_id: UUID,
    ) -> VendorCallAuthorizationV1 | None:
        rows = self._client.select_many(
            "vendor_call_authorizations",
            {
                "job_id": f"eq.{job_id}",
                "job_spec_version": f"eq.{job_spec_version}",
                "vendor_id": f"eq.{vendor_id}",
            },
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise ProviderRequestError(
                "Supabase returned duplicate vendor call authorizations"
            )
        return self._authorization_from_row(rows[0])

    def list_vendor_call_authorizations(
        self,
        job_id: UUID,
        job_spec_version: str,
    ) -> list[VendorCallAuthorizationV1]:
        rows = self._client.select_many(
            "vendor_call_authorizations",
            {
                "job_id": f"eq.{job_id}",
                "job_spec_version": f"eq.{job_spec_version}",
            },
        )
        return sorted(
            (self._authorization_from_row(row) for row in rows),
            key=lambda item: str(item.vendor_id),
        )

    def save_vendor_call_authorization(
        self,
        authorization: VendorCallAuthorizationV1,
    ) -> VendorCallAuthorizationV1:
        candidate = self._copy_vendor_call_authorization(authorization)
        job = self._require_job(candidate.job_id)
        if (
            not job.job_spec.confirmed
            or job.job_spec.locked_version != candidate.job_spec_version
            or job.job_spec.version != candidate.job_spec_version
        ):
            raise DomainConflict(
                "Vendor call authorization requires the locked JobSpec version"
            )
        existing = self.get_vendor_call_authorization(
            candidate.job_id,
            candidate.job_spec_version,
            candidate.vendor_id,
        )
        if existing is not None:
            if existing != candidate:
                raise DomainConflict(
                    "Vendor call authorization is immutable for this JobSpec"
                )
            return existing
        try:
            self._client.insert(
                "vendor_call_authorizations",
                {
                    "id": str(candidate.authorization_id),
                    "job_id": str(candidate.job_id),
                    "job_spec_version": candidate.job_spec_version,
                    "job_spec_sha256": candidate.job_spec_sha256,
                    "vendor_id": str(candidate.vendor_id),
                    "contact_id": str(candidate.contact_id),
                    "normalized_number": candidate.normalized_number,
                    "display_number": candidate.display_number,
                    "number_hash": candidate.number_hash,
                    "recipient_timezone": candidate.recipient_timezone,
                    "consent_method": candidate.consent_method.value,
                    "consent_evidence_reference": (
                        candidate.consent_evidence_reference
                    ),
                    "consented_at": candidate.consented_at.isoformat(),
                    "ai_call_consented": candidate.ai_call_consented,
                    "recording_consented": candidate.recording_consented,
                    "source_url": str(candidate.source_url),
                    "created_at": candidate.created_at.isoformat(),
                },
            )
        except SupabaseDuplicate as exc:
            raise DomainConflict(
                "Vendor call destination is already authorized for this JobSpec"
            ) from exc
        return self._copy_vendor_call_authorization(candidate)

    def get_vendor_suppression(
        self,
        number_hash: str,
    ) -> VendorSuppressionV1 | None:
        rows = self._client.select_many(
            "vendor_call_suppressions",
            {"number_hash": f"eq.{number_hash}"},
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise ProviderRequestError("Supabase returned duplicate suppressions")
        try:
            return VendorSuppressionV1(
                number_hash=rows[0]["number_hash"],
                reason=rows[0]["reason"],
                created_at=rows[0]["created_at"],
            )
        except (KeyError, ValueError) as exc:
            raise ProviderRequestError(
                "Supabase returned an invalid vendor suppression"
            ) from exc

    def save_vendor_suppression(
        self,
        suppression: VendorSuppressionV1,
    ) -> VendorSuppressionV1:
        candidate = self._copy_vendor_suppression(suppression)
        existing = self.get_vendor_suppression(candidate.number_hash)
        if existing is not None:
            return existing
        try:
            self._client.insert(
                "vendor_call_suppressions",
                {
                    "id": str(
                        uuid5(
                            NAMESPACE_URL,
                            f"veramove-vendor-suppression:{candidate.number_hash}",
                        )
                    ),
                    **candidate.model_dump(mode="json"),
                },
            )
        except SupabaseDuplicate as exc:
            existing = self.get_vendor_suppression(candidate.number_hash)
            if existing is None:
                raise ProviderRequestError(
                    "Supabase suppression conflict could not be resolved"
                ) from exc
            return existing
        return self._copy_vendor_suppression(candidate)

    def create_attempt(self, attempt: CallAttempt) -> CallAttempt:
        candidate = self._copy_attempt(attempt)
        self._require_job(candidate.job_id)
        self._persist_vendor(candidate.vendor)
        try:
            self._client.insert("call_attempts", self._attempt_row(candidate))
        except SupabaseDuplicate as exc:
            raise DuplicateResource(f"Call attempt {candidate.call_id} already exists") from exc
        return self._copy_attempt(candidate)

    def save_attempt(self, attempt: CallAttempt) -> CallAttempt:
        candidate = self._copy_attempt(attempt)
        if self.get_attempt(candidate.call_id) is None:
            raise ResourceNotFound(f"Call attempt {candidate.call_id} was not found")
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
        return [CallAttempt.model_validate(deepcopy(row["payload"])) for row in rows]

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
        record.calls = [item for item in record.calls if item.call_id != candidate.call_id]
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
        return [CallRecord.model_validate(deepcopy(row["payload"])) for row in rows]

    def reserve_webhook(self, idempotency_key: str) -> bool:
        """Compatibility path for legacy normalized events; new voice flows use leases."""

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

    def claim_voice_webhook_receipt(
        self,
        lease: VoiceWebhookLease,
    ) -> VoiceWebhookClaimResult:
        candidate = VoiceWebhookLease.model_validate(lease.model_dump(mode="python"))
        response = self._client.rpc(
            "veramove_claim_voice_webhook_receipt",
            {
                "p_idempotency_key": candidate.idempotency_key,
                "p_event_type": candidate.event_type,
                "p_lease_token": str(candidate.lease_token),
                "p_lease_expires_at": candidate.lease_expires_at.isoformat(),
                "p_now": candidate.now.isoformat(),
            },
        )
        try:
            return VoiceWebhookClaimResult.model_validate(response)
        except ValueError as exc:
            raise ProviderRequestError("Supabase voice receipt response was invalid") from exc

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
        response = self._client.rpc(
            "veramove_fail_voice_webhook_receipt",
            {
                "p_idempotency_key": request.idempotency_key,
                "p_lease_token": str(request.lease_token),
                "p_failure_code": request.failure_code,
                "p_retryable": request.retryable,
                "p_now": request.now.isoformat(),
            },
        )
        try:
            return VoiceWebhookFailureResult.model_validate(response)
        except ValueError as exc:
            raise ProviderRequestError("Supabase voice receipt response was invalid") from exc

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
        external_call_id = (
            candidate.attempt.reference.provider_call_id
            if candidate.attempt.reference is not None
            else None
        )
        quote_row = self._quote_row(candidate.quote) if candidate.quote is not None else None
        evidence_rows = (
            [
                self._evidence_row(candidate.quote, evidence)
                for evidence in candidate.quote.transcript_evidence
            ]
            if candidate.quote is not None
            else []
        )
        job_row = {
            **self._job_row(candidate.job),
            "expected_revision": candidate.expected_revision,
        }
        event = self._safe_event(candidate.event)
        response = self._client.rpc(
            "veramove_finalize_voice_webhook",
            {
                "p_idempotency_key": request.idempotency_key,
                "p_lease_token": str(request.lease_token),
                "p_attempt": self._attempt_row(candidate.attempt),
                "p_call": self._call_row(candidate.call, external_call_id),
                "p_quote": quote_row,
                "p_evidence": evidence_rows,
                "p_job": job_row,
                "p_event": {
                    "id": str(event.event_id),
                    "job_id": str(event.job_id),
                    "call_id": str(event.call_id) if event.call_id is not None else None,
                    "event_type": event.event_type,
                    "idempotency_key": request.idempotency_key,
                    "data_classification": candidate.job.job_spec.data_classification.value,
                    "payload": event.model_dump(mode="json"),
                },
                "p_now": request.now.isoformat(),
            },
        )
        try:
            return VoiceWebhookFinalizeResult.model_validate(response)
        except ValueError as exc:
            raise ProviderRequestError("Supabase voice finalization response was invalid") from exc

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
        session_row = self._intake_session_row(candidate.session)
        if isinstance(candidate, VoiceIntakeCompletion):
            safe_event = self._safe_event(candidate.event)
            job_row: dict[str, Any] | None = self._job_row(candidate.job)
            event_row: dict[str, Any] = {
                "id": str(safe_event.event_id),
                "job_id": str(safe_event.job_id),
                "call_id": None,
                "event_type": safe_event.event_type,
                "idempotency_key": request.idempotency_key,
                "data_classification": candidate.job.job_spec.data_classification.value,
                "payload": safe_event.model_dump(mode="json"),
            }
        else:
            job_row = None
            event_row = {"event_type": candidate.event_type}
        response = self._client.rpc(
            "veramove_finalize_voice_intake_webhook",
            {
                "p_idempotency_key": request.idempotency_key,
                "p_lease_token": str(request.lease_token),
                "p_schema_version": "2026-07-21.2",
                "p_kind": candidate.kind,
                "p_session": session_row,
                "p_job": job_row,
                "p_event": event_row,
                "p_now": request.now.isoformat(),
            },
        )
        try:
            return VoiceWebhookFinalizeResult.model_validate(response)
        except ValueError as exc:
            raise ProviderRequestError(
                "Supabase voice intake finalization response was invalid"
            ) from exc

    def get_job_revision(self, job_id: UUID) -> int:
        rows = self._client.select_many("jobs", {"id": f"eq.{job_id}"})
        if not rows:
            raise ResourceNotFound(f"Job {job_id} was not found")
        revision = rows[0].get("aggregate_revision", 0)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise ProviderRequestError("Supabase job revision was invalid")
        return revision

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
                    "data_classification": self._job_classification(safe_event.job_id),
                    "payload": safe_event.model_dump(mode="json"),
                    "created_at": safe_event.occurred_at.isoformat(),
                },
            )
        except SupabaseDuplicate as exc:
            raise DuplicateResource(f"Job event {safe_event.event_id} already exists") from exc
        return self._copy_event(safe_event)

    def list_events(self, job_id: UUID) -> list[JobEvent]:
        rows = self._client.select_many(
            "event_log",
            {
                "job_id": f"eq.{job_id}",
                "source": "eq.veramove",
            },
        )
        return [JobEvent.model_validate(deepcopy(row["payload"])) for row in rows]

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
        record.quotes = [item for item in record.quotes if item.quote_id != candidate.quote_id]
        record.quotes.append(candidate)
        self.save(record)
        return self._copy_quote(candidate)

    def list_quotes(self, job_id: UUID) -> list[QuoteV1]:
        rows = self._client.select_many(
            "quotes",
            {"job_id": f"eq.{job_id}"},
        )
        return [QuoteV1.model_validate(deepcopy(row["payload"])) for row in rows]

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
        if self.get(candidate.job_id) is not None:
            raise DomainConflict("Intake session must exist before its canonical JobRecord")
        try:
            self._client.insert(
                "intake_sessions",
                self._intake_session_row(candidate),
            )
        except SupabaseDuplicate as exc:
            if candidate.provider_call_key_hash is not None:
                replay = self.find_intake_session_by_provider_call_key_hash(
                    candidate.provider_call_key_hash
                )
                if replay is not None:
                    return replay
            raise DuplicateResource(
                f"Intake session {candidate.intake_session_id} already exists"
            ) from exc
        return self._copy_intake_session(candidate)

    def get_intake_session(self, session_id: UUID) -> IntakeSession | None:
        rows = self._client.select_many(
            "intake_sessions",
            {"id": f"eq.{session_id}"},
        )
        if not rows:
            return None
        return self._intake_session_from_row(rows[0])

    def find_intake_session_by_provider_call_key_hash(
        self,
        provider_call_key_hash: str,
    ) -> IntakeSession | None:
        rows = self._client.select_many(
            "intake_sessions",
            {"provider_call_key_hash": f"eq.{provider_call_key_hash}"},
        )
        if not rows:
            return None
        return self._intake_session_from_row(rows[0])

    def find_intake_session_by_conversation_id(
        self,
        conversation_id: str,
    ) -> IntakeSession | None:
        rows = self._client.select_many(
            "intake_sessions",
            {"conversation_id": f"eq.{conversation_id}"},
        )
        if not rows:
            return None
        return self._intake_session_from_row(rows[0])

    def save_intake_session(self, session: IntakeSession) -> IntakeSession:
        candidate = self._copy_intake_session(session)
        current = self.get_intake_session(candidate.intake_session_id)
        if current is None:
            raise ResourceNotFound(f"Intake session {candidate.intake_session_id} was not found")
        validate_intake_session_update(current, candidate)
        if candidate.conversation_id is not None:
            owner = self.find_intake_session_by_conversation_id(candidate.conversation_id)
            if owner is not None and owner.intake_session_id != candidate.intake_session_id:
                raise DuplicateResource("An intake session already owns this conversation")
        self._client.upsert(
            "intake_sessions",
            self._intake_session_row(candidate),
            on_conflict="id",
        )
        return self._copy_intake_session(candidate)

    def reserve_intake_browser_credential(
        self,
        session_id: UUID,
        issued_at: datetime,
    ) -> IntakeSession:
        payload = self._client.rpc(
            "veramove_reserve_browser_voice_credential",
            {
                "p_session_id": str(session_id),
                "p_issued_at": issued_at.isoformat(),
            },
        )
        if not isinstance(payload, dict):
            raise ProviderRequestError("Supabase returned an invalid intake reservation")
        return self._intake_session_from_row(payload)

    def claim_intake_resume(
        self,
        session_id: UUID,
        child: IntakeSession,
        now: datetime,
    ) -> IntakeSession:
        source = self.get_intake_session(session_id)
        if source is None:
            raise ResourceNotFound(f"Intake session {session_id} was not found")
        if source.recovery_action is IntakeRecoveryAction.RESUME:
            assert source.recovery_target_id is not None
            existing = self.get_intake_session(source.recovery_target_id)
            if existing is None:
                raise DomainConflict("Intake resume target is missing")
            return existing
        if source.recovery_action is not None:
            raise DomainConflict("Incomplete intake already has a recovery action")
        _validate_resume_candidate(source, child, now)
        payload = self._client.rpc(
            "veramove_claim_intake_resume",
            {
                "p_session_id": str(session_id),
                "p_child": self._intake_session_row(child),
                "p_now": now.isoformat(),
            },
        )
        if not isinstance(payload, dict):
            raise ProviderRequestError("Supabase returned an invalid intake resume")
        try:
            saved = self._intake_session_from_row(payload)
        except (KeyError, ValueError) as exc:
            raise ProviderRequestError("Supabase returned an invalid intake resume") from exc
        if saved != child:
            raise ProviderRequestError("Supabase intake resume did not match the request")
        return saved

    def finish_intake_manually(
        self,
        session_id: UUID,
        job: JobRecord,
        now: datetime,
    ) -> JobRecord:
        source = self.get_intake_session(session_id)
        if source is None:
            raise ResourceNotFound(f"Intake session {session_id} was not found")
        if source.recovery_action is IntakeRecoveryAction.MANUAL:
            assert source.recovery_target_id is not None
            existing = self.get(source.recovery_target_id)
            if existing is None:
                raise DomainConflict("Manual intake recovery job is missing")
            return existing
        if source.recovery_action is not None:
            raise DomainConflict("Incomplete intake already has a recovery action")
        _validate_manual_candidate(source, job, now)
        payload = self._client.rpc(
            "veramove_finish_intake_manually",
            {
                "p_session_id": str(session_id),
                "p_job": self._job_row(job),
                "p_now": now.isoformat(),
            },
        )
        if not isinstance(payload, dict):
            raise ProviderRequestError("Supabase returned an invalid manual intake job")
        try:
            saved = JobRecord.model_validate(deepcopy(payload["payload"]))
        except (KeyError, ValueError) as exc:
            raise ProviderRequestError(
                "Supabase returned an invalid manual intake job"
            ) from exc
        if saved != job:
            raise ProviderRequestError("Supabase manual intake job did not match the request")
        return saved

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
                "provenance": [item.model_dump(mode="json") for item in vendor.provenance],
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
                job_spec.confirmed_at.isoformat() if job_spec.confirmed_at is not None else None
            ),
            "locked_job_spec_version": job_spec.locked_version,
            "data_classification": job_spec.data_classification.value,
            "payload": record.model_dump(mode="json"),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    @staticmethod
    def _copy_vendor_research(
        research: JobVendorResearchV1,
    ) -> JobVendorResearchV1:
        return JobVendorResearchV1.model_validate(
            deepcopy(research.model_dump(mode="json"))
        )

    @staticmethod
    def _copy_vendor_call_authorization(
        authorization: VendorCallAuthorizationV1,
    ) -> VendorCallAuthorizationV1:
        return VendorCallAuthorizationV1.model_validate(
            deepcopy(authorization.model_dump(mode="json"))
        )

    @staticmethod
    def _copy_vendor_suppression(
        suppression: VendorSuppressionV1,
    ) -> VendorSuppressionV1:
        return VendorSuppressionV1.model_validate(
            deepcopy(suppression.model_dump(mode="json"))
        )

    @staticmethod
    def _authorization_from_row(
        row: dict[str, Any],
    ) -> VendorCallAuthorizationV1:
        try:
            return VendorCallAuthorizationV1(
                authorization_id=row["id"],
                job_id=row["job_id"],
                job_spec_version=row["job_spec_version"],
                job_spec_sha256=row["job_spec_sha256"],
                vendor_id=row["vendor_id"],
                contact_id=row["contact_id"],
                normalized_number=row["normalized_number"],
                display_number=row["display_number"],
                number_hash=row["number_hash"],
                recipient_timezone=row["recipient_timezone"],
                consent_method=row["consent_method"],
                consent_evidence_reference=row["consent_evidence_reference"],
                consented_at=row["consented_at"],
                ai_call_consented=row["ai_call_consented"],
                recording_consented=row["recording_consented"],
                source_url=row["source_url"],
                created_at=row["created_at"],
            )
        except (KeyError, ValueError) as exc:
            raise ProviderRequestError(
                "Supabase returned an invalid vendor call authorization"
            ) from exc

    @staticmethod
    def _attempt_row(attempt: CallAttempt) -> dict[str, Any]:
        return {
            "id": str(attempt.call_id),
            "job_id": str(attempt.job_id),
            "vendor_id": str(attempt.vendor.vendor_id),
            "conversation_id": (
                attempt.reference.conversation_id if attempt.reference is not None else None
            ),
            "external_call_id": (
                attempt.reference.provider_call_id if attempt.reference is not None else None
            ),
            "idempotency_key": f"call:{attempt.call_id}",
            "kind": attempt.kind.value,
            "job_spec_version": attempt.job_spec_version,
            "destination_slot": attempt.destination_slot,
            "expected_agent_id": attempt.expected_agent_id,
            "agent_config_version": attempt.agent_config_version,
            "call_mode": attempt.call_mode,
            "job_spec_sha256": attempt.job_spec_sha256,
            "negotiation_context": (
                attempt.negotiation_context.model_dump(mode="json")
                if attempt.negotiation_context is not None
                else {}
            ),
            "provider_version_id": attempt.provider_version_id,
            "status": attempt.status.value,
            "data_classification": attempt.vendor.data_classification.value,
            "payload": attempt.model_dump(mode="json"),
            "created_at": attempt.started_at.isoformat(),
            "updated_at": (attempt.completed_at or attempt.started_at).isoformat(),
        }

    @staticmethod
    def _intake_session_row(session: IntakeSession) -> dict[str, Any]:
        return {
            "id": str(session.intake_session_id),
            "reserved_job_id": str(session.job_id),
            "provider_call_key_hash": session.provider_call_key_hash,
            "conversation_id": session.conversation_id,
            "expected_agent_id": session.expected_agent_id,
            "agent_config_version": session.agent_config_version,
            "data_mode": session.data_mode.value,
            "status": session.status.value,
            "partial_job_spec": (
                session.partial_job_spec.model_dump(mode="json")
                if session.partial_job_spec is not None
                else None
            ),
            "base_job_spec": (
                session.base_job_spec.model_dump(mode="json")
                if session.base_job_spec is not None
                else None
            ),
            "missing_fields": list(session.missing_fields),
            "terminal_reason": session.terminal_reason,
            "recovery_action": (
                session.recovery_action.value
                if session.recovery_action is not None
                else None
            ),
            "recovery_target_id": (
                str(session.recovery_target_id)
                if session.recovery_target_id is not None
                else None
            ),
            "resumed_from_session_id": (
                str(session.resumed_from_session_id)
                if session.resumed_from_session_id is not None
                else None
            ),
            "failure_code": session.failure_code,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "completed_at": (
                session.completed_at.isoformat() if session.completed_at is not None else None
            ),
            "browser_credential_issued_at": (
                session.browser_credential_issued_at.isoformat()
                if session.browser_credential_issued_at is not None
                else None
            ),
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
        call_id = quote.transcript_evidence[0].call_id if quote.transcript_evidence else None
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
            "provenance": [item.model_dump(mode="json") for item in quote.provenance],
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
            and not (isinstance(value, str) and _PHONE_LIKE.search(value) is not None)
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

    @staticmethod
    def _copy_intake_session(session: IntakeSession) -> IntakeSession:
        return IntakeSession.model_validate(deepcopy(session.model_dump(mode="json")))

    @staticmethod
    def _intake_session_from_row(row: dict[str, Any]) -> IntakeSession:
        return IntakeSession.model_validate(
            {
                "intake_session_id": row["id"],
                "job_id": row["reserved_job_id"],
                "provider_call_key_hash": row.get("provider_call_key_hash"),
                "conversation_id": row.get("conversation_id"),
                "expected_agent_id": row["expected_agent_id"],
                "agent_config_version": row["agent_config_version"],
                "data_mode": row.get("data_mode", "supervised_role_play"),
                "status": row["status"],
                "partial_job_spec": row.get("partial_job_spec"),
                "base_job_spec": row.get("base_job_spec"),
                "missing_fields": row.get("missing_fields") or [],
                "terminal_reason": row.get("terminal_reason"),
                "recovery_action": row.get("recovery_action"),
                "recovery_target_id": row.get("recovery_target_id"),
                "resumed_from_session_id": row.get("resumed_from_session_id"),
                "failure_code": row.get("failure_code"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "completed_at": row.get("completed_at"),
                "browser_credential_issued_at": row.get(
                    "browser_credential_issued_at"
                ),
            }
        )

def _validate_resume_candidate(
    source: IntakeSession,
    child: IntakeSession,
    now: datetime,
) -> None:
    if source.status is not IntakeSessionStatus.INCOMPLETE or source.partial_job_spec is None:
        raise DomainConflict("Only incomplete intake sessions can resume")
    expected_base = source.partial_job_spec.model_copy(
        update={"job_id": child.job_id},
        deep=True,
    )
    if (
        child.status is not IntakeSessionStatus.PENDING
        or child.resumed_from_session_id != source.intake_session_id
        or child.base_job_spec != expected_base
        or child.data_mode is not source.data_mode
        or child.expected_agent_id != source.expected_agent_id
        or child.agent_config_version != source.agent_config_version
        or child.provider_call_key_hash is not None
        or child.created_at != now
        or child.updated_at != now
    ):
        raise DomainConflict("Intake resume child does not match its source")


def _validate_manual_candidate(
    source: IntakeSession,
    job: JobRecord,
    now: datetime,
) -> None:
    if source.status is not IntakeSessionStatus.INCOMPLETE or source.partial_job_spec is None:
        raise DomainConflict("Only incomplete intake sessions can finish manually")
    if (
        job.job_spec != source.partial_job_spec
        or job.state is not JobState.INTAKE_COMPLETE
        or job.created_at != now
        or job.updated_at != now
        or job.calls
        or job.quotes
        or job.recommendation is not None
    ):
        raise DomainConflict("Manual intake job does not match the partial spec")


__all__ = ["SupabaseRepository"]
