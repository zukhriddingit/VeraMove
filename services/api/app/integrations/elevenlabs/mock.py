"""Synthetic call outcomes with no telephony or network activity."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from services.api.app.contracts import (
    CallOutcome,
    CallOutcomeType,
    CallRecord,
    CallStatus,
    JobSpecV1,
    Vendor,
)
from services.api.app.integrations.elevenlabs.base import TwilioTransport
from services.api.app.orchestration.fixtures import DemoFixtures

CALL_IDS = (
    UUID("10000000-0000-4000-8000-000000000001"),
    UUID("10000000-0000-4000-8000-000000000002"),
    UUID("10000000-0000-4000-8000-000000000003"),
)


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
