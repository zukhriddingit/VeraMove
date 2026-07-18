"""Synthetic call outcomes with no telephony or network activity."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from services.api.app.contracts import (
    CallOutcome,
    CallOutcomeType,
    CallRecord,
    CallStatus,
    JobSpecV1,
    QuoteV1,
    Vendor,
)
from services.api.app.core.errors import ResourceNotFound
from services.api.app.integrations.elevenlabs.base import TwilioTransport
from services.api.app.orchestration.fixtures import DemoFixtures
from services.api.app.orchestration.models import VoiceCallReference, VoiceCallResult

CALL_IDS = (
    UUID("10000000-0000-4000-8000-000000000001"),
    UUID("10000000-0000-4000-8000-000000000002"),
    UUID("10000000-0000-4000-8000-000000000003"),
)


def mock_completed_at() -> datetime:
    """Return a stable synthetic timestamp for deterministic provider results."""

    return datetime(2026, 7, 18, 17, 0, tzinfo=UTC)


class MockTwilioTransport:
    """Create a non-dialable synthetic reference instead of placing a call."""

    def create_call_reference(self, vendor: Vendor, job_spec: JobSpecV1) -> str:
        return f"synthetic-twilio-{job_spec.job_id}-{vendor.slug}"


class MockVoiceVendorGateway:
    def __init__(
        self,
        fixtures: DemoFixtures,
        transport: TwilioTransport | None = None,
    ) -> None:
        self._fixtures = fixtures
        self._transport = transport or MockTwilioTransport()

    def create_calls(self, job_spec: JobSpecV1) -> list[CallRecord]:
        quotes = self._fixtures.load_initial_quotes()
        started = datetime(2026, 7, 18, 16, 0, tzinfo=UTC)
        calls: list[CallRecord] = []
        for index, quote in enumerate(quotes):
            provisional = dict(quote.provisional_data)
            provisional["twilio_transport_reference"] = self._transport.create_call_reference(
                quote.vendor,
                job_spec,
            )
            quote = quote.model_copy(
                update={"job_id": job_spec.job_id, "provisional_data": provisional},
            )
            calls.append(
                CallRecord(
                    call_id=CALL_IDS[index],
                    job_id=job_spec.job_id,
                    vendor=quote.vendor,
                    status=CallStatus.COMPLETED,
                    started_at=started + timedelta(minutes=index * 5),
                    completed_at=started + timedelta(minutes=index * 5 + 3),
                    outcome=CallOutcome(type=CallOutcomeType.ITEMIZED_QUOTE, quote=quote),
                    recording_url=quote.recording_url,
                )
            )
        return calls


class MockVoiceProvider:
    """Implement one synchronous synthetic call at a time."""

    initial_call_limit = 3

    def __init__(
        self,
        fixtures: DemoFixtures,
        clock: Callable[[], datetime] = mock_completed_at,
    ) -> None:
        self._fixtures = fixtures
        self._clock = clock

    def initiate_quote_call(
        self,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
    ) -> VoiceCallResult:
        fixture_quote = next(
            (
                quote
                for quote in self._fixtures.load_initial_quotes()
                if quote.vendor.vendor_id == vendor.vendor_id
            ),
            None,
        )
        if fixture_quote is None:
            raise ResourceNotFound(
                f"No synthetic quote exists for vendor {vendor.vendor_id}",
            )
        quote = self._rebind_quote(fixture_quote, job_spec, vendor, call_id)
        return self._result(job_spec, vendor, call_id, quote, "quote")

    def initiate_negotiation_call(
        self,
        job_spec: JobSpecV1,
        target_vendor: Vendor,
        verified_competitor: QuoteV1,
        planned_quote: QuoteV1,
        call_id: UUID,
    ) -> VoiceCallResult:
        del verified_competitor
        quote = self._rebind_quote(
            planned_quote,
            job_spec,
            target_vendor,
            call_id,
        )
        return self._result(
            job_spec,
            target_vendor,
            call_id,
            quote,
            "negotiation",
        )

    def _result(
        self,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
        quote: QuoteV1,
        kind: str,
    ) -> VoiceCallResult:
        return VoiceCallResult(
            reference=VoiceCallReference(
                conversation_id=f"synthetic-conversation-{call_id}",
                provider_call_id=(
                    f"synthetic-twilio-{kind}-{job_spec.job_id}-{vendor.slug}"
                ),
            ),
            outcome=CallOutcome(type=CallOutcomeType.ITEMIZED_QUOTE, quote=quote),
            recording_url=quote.recording_url,
            completed_at=self._clock(),
        )

    @staticmethod
    def _rebind_quote(
        quote: QuoteV1,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
    ) -> QuoteV1:
        evidence = [
            item.model_copy(update={"call_id": call_id}, deep=True)
            for item in quote.transcript_evidence
        ]
        return quote.model_copy(
            update={
                "job_id": job_spec.job_id,
                "vendor": vendor.model_copy(deep=True),
                "job_spec_version": job_spec.version,
                "transcript_evidence": evidence,
            },
            deep=True,
        )
