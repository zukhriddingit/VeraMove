"""Validated tool facade for voice-agent writes and negotiation leverage."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import HttpUrl

from services.api.app.contracts import (
    CallOutcome,
    CallOutcomeType,
    CallRecord,
    CallStatus,
    QuoteV1,
    VerificationStatus,
)
from services.api.app.core.errors import DomainConflict, ResourceNotFound
from services.api.app.orchestration.models import CallAttempt
from services.api.app.repositories.base import CallRepository, QuoteRepository


def utc_now() -> datetime:
    return datetime.now(UTC)


class VoiceTools:
    """Enforce call ownership and evidence rules before repository writes."""

    def __init__(
        self,
        calls: CallRepository,
        quotes: QuoteRepository,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._calls = calls
        self._quotes = quotes
        self._clock = clock

    def save_quote(self, call_id: UUID, quote: QuoteV1) -> QuoteV1:
        attempt = self._require_attempt(call_id)
        self._validate_quote(attempt, quote)
        return self._quotes.save_quote(quote)

    def save_call_outcome(
        self,
        call_id: UUID,
        outcome: CallOutcome,
        completed_at: datetime,
        recording_url: HttpUrl | str,
    ) -> CallRecord:
        attempt = self._require_attempt(call_id)
        if completed_at is None:
            raise DomainConflict("Completed calls require a completed timestamp")
        if completed_at.tzinfo is None or completed_at.utcoffset() is None:
            raise DomainConflict("Completed timestamp must include a timezone")
        if completed_at < attempt.started_at:
            raise DomainConflict("Call completion cannot precede call start")
        if recording_url is None or not str(recording_url).strip():
            raise DomainConflict("Completed calls require a recording URL")

        quote = outcome.quote
        if quote is not None:
            self._validate_quote(attempt, quote)

        status = (
            CallStatus.FAILED
            if outcome.type is CallOutcomeType.FAILED
            else CallStatus.COMPLETED
        )
        completed_attempt = attempt.model_copy(
            update={"status": status, "completed_at": completed_at},
            deep=True,
        )
        call = CallRecord(
            call_id=attempt.call_id,
            job_id=attempt.job_id,
            vendor=attempt.vendor,
            status=status,
            started_at=attempt.started_at,
            completed_at=completed_at,
            outcome=outcome,
            recording_url=recording_url,
        )
        if quote is not None:
            self._quotes.save_quote(quote)
        self._calls.save_attempt(completed_attempt)
        return self._calls.save_call(call)

    def get_verified_competing_quote(
        self,
        job_id: UUID,
        target_vendor_id: UUID,
        job_spec_version: str,
    ) -> QuoteV1:
        quote = self._quotes.get_verified_competing_quote(
            job_id,
            target_vendor_id,
            job_spec_version,
        )
        if quote is None:
            raise DomainConflict("Negotiation requires a verified competing quote")
        return quote

    def request_callback(
        self,
        call_id: UUID,
        callback_at: datetime,
        recording_url: HttpUrl | str,
    ) -> CallRecord:
        return self.save_call_outcome(
            call_id,
            CallOutcome(
                type=CallOutcomeType.CALLBACK_COMMITMENT,
                callback_at=callback_at,
            ),
            self._clock(),
            recording_url,
        )

    def _require_attempt(self, call_id: UUID) -> CallAttempt:
        attempt = self._calls.get_attempt(call_id)
        if attempt is None:
            raise ResourceNotFound(f"Call attempt {call_id} was not found")
        return attempt

    @staticmethod
    def _validate_quote(attempt: CallAttempt, quote: QuoteV1) -> None:
        if quote.job_id != attempt.job_id:
            raise DomainConflict("Quote job does not match call attempt")
        if quote.vendor.vendor_id != attempt.vendor.vendor_id:
            raise DomainConflict("Quote vendor does not match call attempt")
        if quote.job_spec_version != attempt.job_spec_snapshot.version:
            raise DomainConflict("Quote JobSpec version does not match call attempt")
        if any(
            evidence.call_id != attempt.call_id
            for evidence in quote.transcript_evidence
        ):
            raise DomainConflict("Quote evidence does not match call attempt")
        if quote.verification_status is VerificationStatus.VERIFIED and (
            not quote.verified_data or not quote.transcript_evidence
        ):
            raise DomainConflict("Verified quotes require evidence and verified data")
