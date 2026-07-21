"""Versioned contracts for source-backed, unverified vendor website research."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, HttpUrl, field_validator, model_validator

from services.api.app.contracts.models import (
    ContractModel,
    DataClassification,
    FeeCategory,
    Vendor,
    VendorSearchQuery,
)


class WebsiteClaimKind(StrEnum):
    """Allowed website statements; fee values intentionally mirror FeeCategory."""

    BASE_SERVICE = "base_service"
    HOURLY_MINIMUM = "hourly_minimum"
    TRAVEL = "travel"
    FUEL = "fuel"
    STAIRS = "stairs"
    ELEVATOR = "elevator"
    LONG_CARRY = "long_carry"
    PACKING = "packing"
    MATERIALS = "materials"
    DISASSEMBLY = "disassembly"
    STORAGE = "storage"
    INSURANCE = "insurance"
    TAX = "tax"
    DEPOSIT = "deposit"
    OTHER = "other"
    HOURLY_RATE = "hourly_rate"
    MINIMUM_HOURS = "minimum_hours"
    MOVER_COUNT = "mover_count"
    SERVICE = "service"
    AVAILABILITY = "availability"
    BINDING = "binding"


class WebsiteResearchClaimDraft(ContractModel):
    """Strict model-facing claim fields before trusted metadata is attached."""

    kind: WebsiteClaimKind
    summary: str = Field(min_length=1, max_length=500)
    advertised_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    unit: str | None = Field(default=None, max_length=80)
    qualifiers: list[str] = Field(default_factory=list, max_length=8)
    source_excerpt: str = Field(min_length=1, max_length=500)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @field_validator("qualifiers")
    @classmethod
    def bound_qualifiers(cls, values: list[str]) -> list[str]:
        if any(len(value) > 120 for value in values):
            raise ValueError("claim qualifiers must be at most 120 characters")
        return values


class WebsiteResearchClaimV1(WebsiteResearchClaimDraft):
    """One bounded webpage-supported statement that is never call evidence."""

    claim_id: UUID = Field(default_factory=uuid4)
    source_url: HttpUrl
    retrieved_at: datetime
    classification: Literal["unverified_website_claim"] = (
        "unverified_website_claim"
    )

    @field_validator("source_url")
    @classmethod
    def require_https_source(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("website research sources must use HTTPS")
        return value

    @field_validator("retrieved_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must include a timezone")
        return value


class VendorVerificationQuestionV1(ContractModel):
    """One deterministic future-call question derived from claims or omissions."""

    question_id: UUID = Field(default_factory=uuid4)
    category: FeeCategory | WebsiteClaimKind
    question: str = Field(min_length=1, max_length=500)
    reason: Literal[
        "published_claim",
        "missing_information",
        "ambiguous_claim",
    ]
    claim_ids: list[UUID] = Field(default_factory=list, max_length=20)


class VendorResearchDossierV1(ContractModel):
    """Persisted website research for one selected real or synthetic vendor."""

    vendor: Vendor
    status: Literal["pending", "complete", "partial", "failed"]
    claims: list[WebsiteResearchClaimV1] = Field(default_factory=list, max_length=20)
    missing_fee_categories: list[FeeCategory] = Field(
        default_factory=list,
        max_length=len(FeeCategory),
    )
    verification_questions: list[VendorVerificationQuestionV1] = Field(
        default_factory=list,
        max_length=40,
    )
    researched_at: datetime | None = None
    safe_failure_reason: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def status_matches_payload(self) -> VendorResearchDossierV1:
        if self.researched_at is not None and (
            self.researched_at.tzinfo is None
            or self.researched_at.utcoffset() is None
        ):
            raise ValueError("researched_at must include a timezone")

        has_research = bool(
            self.claims
            or self.missing_fee_categories
            or self.verification_questions
            or self.researched_at
            or self.safe_failure_reason
        )
        if self.status == "pending" and has_research:
            raise ValueError("pending dossiers cannot contain research results")
        if self.status != "pending" and self.researched_at is None:
            raise ValueError("terminal dossiers require researched_at")
        if self.status == "complete" and self.safe_failure_reason is not None:
            raise ValueError("complete dossiers cannot contain a failure reason")
        if self.status == "partial" and (
            not self.claims or not self.safe_failure_reason
        ):
            raise ValueError("partial dossiers require claims and a failure reason")
        if self.status == "failed" and (
            self.claims or not self.safe_failure_reason
        ):
            raise ValueError("failed dossiers require only a safe failure reason")
        return self


class VendorShortlistRequest(ContractModel):
    """Browser request containing IDs only, never Vendor objects or URLs."""

    vendor_ids: list[UUID] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def require_distinct_ids(self) -> VendorShortlistRequest:
        if len(set(self.vendor_ids)) != 3:
            raise ValueError("vendor_ids must contain exactly three distinct IDs")
        return self


class JobVendorResearchV1(ContractModel):
    """Durable discovery, shortlist, and dossier state for one locked JobSpec."""

    job_id: UUID
    job_spec_version: Literal["1.0"]
    query: VendorSearchQuery
    candidates: list[Vendor] = Field(max_length=10)
    selected_vendor_ids: list[UUID] = Field(default_factory=list, max_length=3)
    dossiers: list[VendorResearchDossierV1] = Field(default_factory=list, max_length=3)
    source: Literal["tavily", "synthetic_mock"]
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_state(self) -> JobVendorResearchV1:
        candidate_ids = [item.vendor_id for item in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("research candidates must be distinct")

        selected = self.selected_vendor_ids
        if selected and (len(selected) != 3 or len(set(selected)) != 3):
            raise ValueError(
                "selected_vendor_ids must contain exactly three distinct IDs"
            )
        if not set(selected).issubset(set(candidate_ids)):
            raise ValueError("selected vendors must come from persisted candidates")

        dossier_ids = [item.vendor.vendor_id for item in self.dossiers]
        if selected and set(dossier_ids) != set(selected):
            raise ValueError("dossiers must exactly match selected vendors")
        if not selected and dossier_ids:
            raise ValueError("dossiers require a saved shortlist")
        if len(dossier_ids) != len(set(dossier_ids)):
            raise ValueError("vendor dossiers must be distinct")

        if self.source == "tavily" and any(
            item.data_classification is not DataClassification.REAL_REDACTED
            for item in self.candidates
        ):
            raise ValueError("Tavily candidates must be classified real_redacted")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("updated_at must include a timezone")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class WebsiteClaimExtractionResult(ContractModel):
    """Strict provider-facing envelope; orchestration adds trusted IDs and source metadata."""

    claims: list[WebsiteResearchClaimDraft] = Field(default_factory=list, max_length=20)


__all__ = [
    "JobVendorResearchV1",
    "VendorResearchDossierV1",
    "VendorShortlistRequest",
    "VendorVerificationQuestionV1",
    "WebsiteClaimExtractionResult",
    "WebsiteClaimKind",
    "WebsiteResearchClaimDraft",
    "WebsiteResearchClaimV1",
]
