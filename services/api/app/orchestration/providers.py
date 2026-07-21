"""Provider-neutral protocols consumed by VeraMove orchestration."""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.api.app.contracts import (
    CallContext,
    FeeCategory,
    JobSpecV1,
    QuoteV1,
    QuoteVerificationResult,
    TranscriptQuoteFacts,
    Vendor,
    VendorCallPlanV1,
)
from services.api.app.orchestration.models import VoiceCallResult


class VoiceCallDestination(BaseModel):
    """Provider-neutral destination resolved without persisting a raw number in attempts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_context: CallContext
    destination_slot: Literal[0, 1, 2]
    authorization_id: UUID | None = None
    normalized_number: str | None = Field(
        default=None,
        pattern=r"^\+1[2-9]\d{9}$",
        exclude=True,
        repr=False,
    )
    number_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    recording_consented: bool

    @model_validator(mode="after")
    def context_matches_destination(self) -> VoiceCallDestination:
        official_fields = (
            self.authorization_id,
            self.normalized_number,
            self.number_hash,
        )
        if self.call_context is CallContext.OFFICIAL_BUSINESS:
            if any(value is None for value in official_fields):
                raise ValueError(
                    "official-business destinations require authorization and number"
                )
            if not self.recording_consented:
                raise ValueError(
                    "official-business destinations require recording consent"
                )
        elif any(value is not None for value in official_fields):
            raise ValueError(
                "supervised role-play destinations cannot contain official contact data"
            )
        return self

    @classmethod
    def supervised_role_play(
        cls,
        destination_slot: Literal[0, 1, 2],
    ) -> VoiceCallDestination:
        return cls(
            call_context=CallContext.SUPERVISED_ROLE_PLAY,
            destination_slot=destination_slot,
            recording_consented=True,
        )


class VoiceProvider(Protocol):
    """Initiate one provider-neutral quote or negotiation call."""

    initial_call_limit: int

    def initiate_quote_call(
        self,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
        destination: VoiceCallDestination,
        call_plan: VendorCallPlanV1 | None,
    ) -> VoiceCallResult: ...

    def initiate_negotiation_call(
        self,
        job_spec: JobSpecV1,
        target_vendor: Vendor,
        verified_competitor: QuoteV1,
        planned_quote: QuoteV1,
        call_id: UUID,
        destination: VoiceCallDestination,
        call_plan: VendorCallPlanV1 | None,
    ) -> VoiceCallResult: ...


class IntelligenceProvider(Protocol):
    """Convert intake and plan negotiation without naming a model vendor."""

    def extract_document(self, document_text: str) -> JobSpecV1: ...

    def negotiate(
        self,
        job_spec: JobSpecV1,
        quotes: list[QuoteV1],
        verified_competitor: QuoteV1,
    ) -> QuoteV1: ...


class QuoteVerificationGateway(Protocol):
    """Verify provisional values against bounded timestamped call evidence."""

    def verify(
        self,
        provisional_quote: QuoteV1,
        transcript_facts: TranscriptQuoteFacts,
        required_fee_categories: set[FeeCategory] | None = None,
    ) -> QuoteVerificationResult: ...
