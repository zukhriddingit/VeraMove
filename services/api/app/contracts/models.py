"""Versioned Pydantic contracts for VeraMove's mock negotiation workflow."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ContractModel(BaseModel):
    """Base model with strict input handling for stable API contracts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class JobState(StrEnum):
    DRAFT = "draft"
    INTAKE_COMPLETE = "intake_complete"
    CONFIRMED = "confirmed"
    CALLING = "calling"
    QUOTES_READY = "quotes_ready"
    NEGOTIATING = "negotiating"
    COMPLETED = "completed"
    FAILED = "failed"


class CallOutcomeType(StrEnum):
    ITEMIZED_QUOTE = "itemized_quote"
    CALLBACK_COMMITMENT = "callback_commitment"
    DOCUMENTED_DECLINE = "documented_decline"
    FAILED = "failed"


class CallStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class VerificationStatus(StrEnum):
    PROVISIONAL = "provisional"
    PARTIALLY_VERIFIED = "partially_verified"
    VERIFIED = "verified"


class BindingType(StrEnum):
    BINDING = "binding"
    NON_BINDING = "non_binding"


class DwellingType(StrEnum):
    APARTMENT = "apartment"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    HOUSE = "house"
    STORAGE_UNIT = "storage_unit"
    OTHER = "other"


class FeeCategory(StrEnum):
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
    TAXES = "taxes"
    DEPOSIT = "deposit"
    OTHER = "other"


class SourceContext(ContractModel):
    intake_method: Literal["voice", "document", "demo"] = "demo"
    vera_user_id: str | None = None
    vera_property_id: str | None = None


class OriginDestinationAccess(ContractModel):
    address_summary: str = Field(min_length=1, max_length=200)
    dwelling_type: DwellingType
    floors: int = Field(default=1, ge=0, le=100)
    stairs: int = Field(default=0, ge=0, le=500)
    elevator_access: bool = False
    parking_distance_feet: int = Field(default=0, ge=0, le=5000)
    access_notes: str | None = Field(default=None, max_length=500)


class InventoryItem(ContractModel):
    item_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(default=1, ge=1, le=1000)
    room: str = Field(min_length=1, max_length=80)
    oversized: bool = False
    fragile: bool = False
    notes: str | None = Field(default=None, max_length=300)


class MovingServices(ContractModel):
    packing: bool = False
    disassembly: bool = False
    storage: bool = False
    storage_days: int | None = Field(default=None, ge=1, le=365)

    @model_validator(mode="after")
    def storage_days_match_storage_request(self) -> MovingServices:
        if self.storage and self.storage_days is None:
            raise ValueError("storage_days is required when storage is requested")
        if not self.storage and self.storage_days is not None:
            raise ValueError("storage_days requires storage=true")
        return self


class JobSpecV1(ContractModel):
    job_id: UUID = Field(default_factory=uuid4)
    version: Literal["1.0"] = "1.0"
    move_date: date
    date_flexible: bool = False
    origin: OriginDestinationAccess
    destination: OriginDestinationAccess
    bedroom_count: int = Field(ge=0, le=20)
    inventory: list[InventoryItem] = Field(min_length=1)
    oversized_or_fragile_items: list[str] = Field(default_factory=list)
    services: MovingServices = Field(default_factory=MovingServices)
    insurance_preference: str = Field(min_length=1, max_length=120)
    confirmed: bool = False
    confirmed_at: datetime | None = None
    source_context: SourceContext = Field(default_factory=SourceContext)

    @model_validator(mode="after")
    def confirmation_fields_are_consistent(self) -> JobSpecV1:
        if self.confirmed != (self.confirmed_at is not None):
            raise ValueError("confirmed and confirmed_at must be set together")
        return self


class Vendor(ContractModel):
    vendor_id: UUID
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    behavior_summary: str = Field(min_length=1, max_length=500)
    contact_label: str = Field(min_length=1, max_length=120)
    service_areas: list[str] = Field(min_length=1)


class FeeLineItem(ContractModel):
    category: FeeCategory
    description: str = Field(min_length=1, max_length=300)
    amount: Decimal = Field(ge=0, decimal_places=2)
    disclosed_upfront: bool = True


class TranscriptEvidence(ContractModel):
    evidence_id: UUID
    call_id: UUID
    excerpt: str = Field(min_length=1, max_length=1000)
    start_seconds: Decimal = Field(ge=0, decimal_places=2)
    end_seconds: Decimal = Field(ge=0, decimal_places=2)
    claim: str = Field(min_length=1, max_length=300)
    recording_url: HttpUrl

    @model_validator(mode="after")
    def evidence_range_is_ordered(self) -> TranscriptEvidence:
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must not precede start_seconds")
        return self


class QuoteV1(ContractModel):
    quote_id: UUID
    job_id: UUID
    vendor: Vendor
    job_spec_version: Literal["1.0"] = "1.0"
    fee_line_items: list[FeeLineItem] = Field(min_length=1)
    original_total: Decimal = Field(ge=0, decimal_places=2)
    negotiated_total: Decimal = Field(ge=0, decimal_places=2)
    currency: Literal["USD"] = "USD"
    deposit: Decimal = Field(ge=0, decimal_places=2)
    binding_type: BindingType
    availability: str = Field(min_length=1, max_length=200)
    concessions: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    provisional_data: dict[str, Any] = Field(default_factory=dict)
    verified_data: dict[str, Any] = Field(default_factory=dict)
    verification_status: VerificationStatus
    transcript_evidence: list[TranscriptEvidence] = Field(default_factory=list)
    recording_url: HttpUrl


class CallOutcome(ContractModel):
    type: CallOutcomeType
    quote: QuoteV1 | None = None
    callback_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def details_match_type(self) -> CallOutcome:
        if self.type is CallOutcomeType.ITEMIZED_QUOTE and self.quote is None:
            raise ValueError("itemized_quote outcomes require quote")
        if self.type is CallOutcomeType.CALLBACK_COMMITMENT and self.callback_at is None:
            raise ValueError("callback_commitment outcomes require callback_at")
        needs_reason = self.type in {
            CallOutcomeType.DOCUMENTED_DECLINE,
            CallOutcomeType.FAILED,
        }
        if needs_reason and not self.reason:
            raise ValueError(f"{self.type.value} outcomes require reason")
        return self


class CallRecord(ContractModel):
    call_id: UUID
    job_id: UUID
    vendor: Vendor
    status: CallStatus
    started_at: datetime
    completed_at: datetime | None = None
    outcome: CallOutcome
    recording_url: HttpUrl


class RecommendationRanking(ContractModel):
    rank: int = Field(ge=1)
    vendor: Vendor
    quote_id: UUID
    total: Decimal = Field(ge=0, decimal_places=2)
    rationale: list[str] = Field(min_length=1)
    red_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(min_length=1)


class RecommendationV1(ContractModel):
    recommendation_id: UUID
    job_id: UUID
    version: Literal["1.0"] = "1.0"
    generated_at: datetime
    summary: str = Field(min_length=1, max_length=1000)
    winning_vendor_id: UUID
    rankings: list[RecommendationRanking] = Field(min_length=1)
    evidence_ids: list[UUID] = Field(min_length=1)
    transcript_evidence: list[TranscriptEvidence] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)


class JobRecord(ContractModel):
    job_spec: JobSpecV1
    state: JobState
    calls: list[CallRecord] = Field(default_factory=list)
    quotes: list[QuoteV1] = Field(default_factory=list)
    recommendation: RecommendationV1 | None = None
    created_at: datetime
    updated_at: datetime


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"
    mode: Literal["mock"] = "mock"
    service: Literal["veramove-api"] = "veramove-api"


class ElevenLabsWebhookEvent(ContractModel):
    idempotency_key: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=120)
    call_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WebhookAck(ContractModel):
    accepted: bool
    duplicate: bool


class VendorDiscoveryResponse(ContractModel):
    vendors: list[Vendor]
    source: Literal["synthetic_mock"] = "synthetic_mock"


class ErrorDetail(ContractModel):
    code: str
    message: str


class ErrorResponse(ContractModel):
    error: ErrorDetail
