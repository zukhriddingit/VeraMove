"""Strict contracts for reviewed vendor contact and call authorization workflows."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, HttpUrl, model_validator

from services.api.app.contracts.models import ContractModel

_DISPLAY_PHONE = re.compile(r"^\([2-9]\d{2}\) \d{3}-\d{4}$")
_NORMALIZED_PHONE = re.compile(r"^\+1[2-9]\d{9}$")


class CallContext(StrEnum):
    """Separate supervised role-play from consented official-business calls."""

    SUPERVISED_ROLE_PLAY = "supervised_role_play"
    OFFICIAL_BUSINESS = "official_business"


class ConsentMethod(StrEnum):
    """Reviewed evidence types that can establish current recipient consent."""

    DIRECT_RECIPIENT_OPT_IN = "direct_recipient_opt_in"
    EXISTING_BUSINESS_RELATIONSHIP_CONFIRMATION = (
        "existing_business_relationship_confirmation"
    )
    PROVIDER_TEST_DESTINATION = "provider_test_destination"


class SuppressionReason(StrEnum):
    """Reasons an outbound destination must not be called again."""

    RECIPIENT_OPT_OUT = "recipient_opt_out"
    MANUAL_BLOCK = "manual_block"
    INVALID_DESTINATION = "invalid_destination"


class VendorContactCandidateV1(ContractModel):
    """One official-site public business contact with tamper-evident provenance."""

    contact_id: UUID = Field(default_factory=uuid4)
    vendor_id: UUID
    normalized_number: str = Field(
        pattern=r"^\+1[2-9]\d{9}$",
        exclude=True,
        repr=False,
    )
    display_number: str = Field(pattern=r"^\([2-9]\d{2}\) \d{3}-\d{4}$")
    source_url: HttpUrl
    source_excerpt: str = Field(min_length=1, max_length=160)
    source_excerpt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="before")
    @classmethod
    def restore_private_normalized_number(cls, value: Any) -> Any:
        """Reconstruct the private canonical form from the persisted display value."""

        if not isinstance(value, dict) or value.get("normalized_number") is not None:
            return value
        display = value.get("display_number")
        if not isinstance(display, str) or _DISPLAY_PHONE.fullmatch(display) is None:
            return value
        digits = "".join(character for character in display if character.isdigit())
        return {**value, "normalized_number": f"+1{digits}"}

    @model_validator(mode="after")
    def display_matches_normalized(self) -> VendorContactCandidateV1:
        digits = "".join(
            character for character in self.display_number if character.isdigit()
        )
        if (
            _DISPLAY_PHONE.fullmatch(self.display_number) is None
            or _NORMALIZED_PHONE.fullmatch(self.normalized_number) is None
            or self.normalized_number != f"+1{digits}"
        ):
            raise ValueError("display_number must match normalized_number")
        if self.source_url.scheme != "https":
            raise ValueError("vendor contact sources must use HTTPS")
        return self


class VendorCallAuthorizationV1(ContractModel):
    """One immutable consent record bound to a locked JobSpec and destination."""

    authorization_id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    job_spec_version: Literal["1.0"]
    job_spec_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    vendor_id: UUID
    contact_id: UUID
    normalized_number: str = Field(
        pattern=r"^\+1[2-9]\d{9}$",
        exclude=True,
        repr=False,
    )
    display_number: str = Field(pattern=r"^\([2-9]\d{2}\) \d{3}-\d{4}$")
    number_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    recipient_timezone: str = Field(min_length=1, max_length=64)
    consent_method: ConsentMethod
    consent_evidence_reference: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$"
    )
    consented_at: datetime
    ai_call_consented: Literal[True]
    recording_consented: Literal[True]
    source_url: HttpUrl
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def restore_private_normalized_number(cls, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("normalized_number") is not None:
            return value
        display = value.get("display_number")
        if not isinstance(display, str) or _DISPLAY_PHONE.fullmatch(display) is None:
            return value
        digits = "".join(character for character in display if character.isdigit())
        return {**value, "normalized_number": f"+1{digits}"}

    @model_validator(mode="after")
    def validate_authorization(self) -> VendorCallAuthorizationV1:
        digits = "".join(
            character for character in self.display_number if character.isdigit()
        )
        if self.normalized_number != f"+1{digits}":
            raise ValueError("display_number must match normalized_number")
        if self.source_url.scheme != "https":
            raise ValueError("authorization source_url must use HTTPS")
        for name, value in (
            ("consented_at", self.consented_at),
            ("created_at", self.created_at),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must include a timezone")
        if self.consented_at > self.created_at:
            raise ValueError("consented_at cannot follow created_at")
        try:
            ZoneInfo(self.recipient_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("recipient_timezone must be an IANA timezone") from exc
        return self


class VendorSuppressionV1(ContractModel):
    """Hashed do-not-call state; no raw destination is stored in this record."""

    number_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: SuppressionReason
    created_at: datetime

    @model_validator(mode="after")
    def require_aware_timestamp(self) -> VendorSuppressionV1:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return self


class VendorCallPlanWebsiteClaimV1(ContractModel):
    """A bounded unverified website claim supplied as call context, never evidence."""

    claim_id: UUID
    kind: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    summary: str = Field(min_length=1, max_length=300)
    source_url: HttpUrl
    classification: Literal["unverified_website_claim"] = (
        "unverified_website_claim"
    )


class VendorCallPlanQuestionV1(ContractModel):
    """One targeted question copied from the deterministic verification plan."""

    question_id: UUID
    category: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    question: str = Field(min_length=1, max_length=500)
    reason: Literal[
        "published_claim",
        "missing_information",
        "ambiguous_claim",
    ]
    claim_ids: list[UUID] = Field(default_factory=list, max_length=20)


class VendorCallPlanV1(ContractModel):
    """Deterministic, capped quote-call agenda for one locked JobSpec."""

    plan_version: Literal["1.0"] = "1.0"
    vendor_id: UUID
    job_spec_version: Literal["1.0"]
    job_spec_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    website_claims: list[VendorCallPlanWebsiteClaimV1] = Field(
        default_factory=list,
        max_length=5,
    )
    source_urls: list[HttpUrl] = Field(default_factory=list, max_length=5)
    questions: list[VendorCallPlanQuestionV1] = Field(
        min_length=1,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_plan(self) -> VendorCallPlanV1:
        if len(self.source_urls) != len({str(url) for url in self.source_urls}):
            raise ValueError("call plan source URLs must be distinct")
        if len(self.questions) != len(
            {question.question_id for question in self.questions}
        ):
            raise ValueError("call plan questions must be distinct")
        payload = repr(self.model_dump(mode="json"))
        if re.search(r"\+1[2-9]\d{9}", payload):
            raise ValueError("call plans cannot contain destination numbers")
        return self


__all__ = [
    "CallContext",
    "ConsentMethod",
    "SuppressionReason",
    "VendorCallAuthorizationV1",
    "VendorCallPlanV1",
    "VendorCallPlanQuestionV1",
    "VendorCallPlanWebsiteClaimV1",
    "VendorContactCandidateV1",
    "VendorSuppressionV1",
]
