"""Synthetic call outcomes with no telephony or network activity."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import HttpUrl

from services.api.app.contracts import (
    CallOutcome,
    CallOutcomeType,
    DataClassification,
    JobSpecV1,
    QuoteV1,
    Vendor,
    VendorCallPlanV1,
)
from services.api.app.core.errors import ResourceNotFound
from services.api.app.orchestration.fixtures import DemoFixtures
from services.api.app.orchestration.models import VoiceCallReference, VoiceCallResult
from services.api.app.orchestration.providers import VoiceCallDestination


def mock_completed_at() -> datetime:
    """Return a stable synthetic timestamp for deterministic provider results."""

    return datetime(2026, 7, 18, 17, 0, tzinfo=UTC)


ROLE_PLAY_NOTICE = (
    "Role-play simulation only; this is not a claim about the company's "
    "actual pricing, availability, or conduct."
)


class MockVoiceProvider:
    """Implement one synchronous synthetic call at a time."""

    initial_call_limit = 3
    outbound_agent_id = "synthetic-mock-outbound-agent"
    agent_config_version = "mock-v1"

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
        destination: VoiceCallDestination | None = None,
        call_plan: VendorCallPlanV1 | None = None,
    ) -> VoiceCallResult:
        del destination, call_plan
        fixture_quotes = self._fixtures.load_initial_quotes()
        fixture_quote = next(
            (quote for quote in fixture_quotes if quote.vendor.vendor_id == vendor.vendor_id),
            None,
        )
        if fixture_quote is None:
            if vendor.data_classification is not DataClassification.ROLE_PLAY:
                raise ResourceNotFound(
                    f"No synthetic quote exists for vendor {vendor.vendor_id}",
                )
            fixture_quote = fixture_quotes[0]
        quote = self._rebind_quote(fixture_quote, job_spec, vendor, call_id)
        return self._result(job_spec, vendor, call_id, quote, "quote")

    def initiate_negotiation_call(
        self,
        job_spec: JobSpecV1,
        target_vendor: Vendor,
        verified_competitor: QuoteV1,
        planned_quote: QuoteV1,
        call_id: UUID,
        destination: VoiceCallDestination | None = None,
        call_plan: VendorCallPlanV1 | None = None,
    ) -> VoiceCallResult:
        del verified_competitor, destination, call_plan
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
                    f"synthetic-twilio-{kind}-{job_spec.job_id}-{vendor.slug}-{call_id}"
                ),
            ),
            outcome=CallOutcome(type=CallOutcomeType.ITEMIZED_QUOTE, quote=quote),
            recording_url=quote.recording_url,
            completed_at=self._clock(),
        )

    @classmethod
    def _rebind_quote(
        cls,
        quote: QuoteV1,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
    ) -> QuoteV1:
        if vendor.data_classification is DataClassification.ROLE_PLAY:
            return cls._rebind_role_play_quote(quote, job_spec, vendor, call_id)
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

    @staticmethod
    def _rebind_role_play_quote(
        quote: QuoteV1,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
    ) -> QuoteV1:
        recording_url = HttpUrl(f"https://recordings.example.com/role-play/{call_id}")
        total = quote.comparable_total or quote.negotiated_total or quote.headline_total
        total_statement = (
            f"The synthetic comparable total is {total} USD."
            if total is not None
            else "The synthetic comparable total remains unknown."
        )
        evidence = [
            item.model_copy(
                update={
                    "evidence_id": uuid5(
                        NAMESPACE_URL,
                        f"role-play-evidence:{call_id}:{index}",
                    ),
                    "call_id": call_id,
                    "excerpt": f"{ROLE_PLAY_NOTICE} {total_statement}",
                    "claim": ("Synthetic role-play quote evidence only; not a company claim."),
                    "recording_url": recording_url,
                    "data_classification": DataClassification.ROLE_PLAY,
                },
                deep=True,
            )
            for index, item in enumerate(quote.transcript_evidence)
        ]
        provisional_data = dict(quote.provisional_data)
        provisional_data["role_play_notice"] = ROLE_PLAY_NOTICE
        verified_data = dict(quote.verified_data)
        verified_data["role_play_notice"] = ROLE_PLAY_NOTICE
        return quote.model_copy(
            update={
                "quote_id": uuid5(NAMESPACE_URL, f"role-play-quote:{call_id}"),
                "job_id": job_spec.job_id,
                "vendor": vendor.model_copy(deep=True),
                "job_spec_version": job_spec.version,
                "availability": (
                    "Role-play synthetic availability; not a claim about the company."
                ),
                "concessions": [
                    f"Role-play scenario: {concession}" for concession in quote.concessions
                ],
                "red_flags": [],
                "provisional_data": provisional_data,
                "verified_data": verified_data,
                "transcript_evidence": evidence,
                "recording_url": recording_url,
                "data_classification": DataClassification.ROLE_PLAY,
            },
            deep=True,
        )
