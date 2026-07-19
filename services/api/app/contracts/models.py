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
    REJECTED = "rejected"


class BindingType(StrEnum):
    BINDING = "binding"
    NON_BINDING = "non_binding"
    UNKNOWN = "unknown"


class IntakeSource(StrEnum):
    VOICE = "voice"
    DOCUMENT = "document"
    MERGED = "merged"
    DEMO = "demo"


class DataClassification(StrEnum):
    SYNTHETIC = "synthetic"
    ROLE_PLAY = "role_play"
    REAL_REDACTED = "real_redacted"


class AmountStatus(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ProvenanceType(StrEnum):
    DOCUMENT = "document"
    VOICE_INTAKE = "voice_intake"
    AGENT_TOOL = "agent_tool"
    TRANSCRIPT = "transcript"
    DEMO_FIXTURE = "demo_fixture"
    TAVILY = "tavily"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


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
    TAX = "tax"
    DEPOSIT = "deposit"
    OTHER = "other"


class SourceContext(ContractModel):
    vera_user_id: str | None = None
    vera_property_id: str | None = None


class OriginDestinationAccess(ContractModel):
    address_summary: str | None = Field(default=None, min_length=1, max_length=200)
    dwelling_type: DwellingType | None = None
    floors: int | None = Field(default=None, ge=0, le=100)
    stairs: int | None = Field(default=None, ge=0, le=500)
    elevator_access: bool | None = None
    parking_distance_feet: int | None = Field(default=None, ge=0, le=5000)
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
    packing: bool | None = None
    disassembly: bool | None = None
    storage: bool | None = None
    storage_days: int | None = Field(default=None, ge=1, le=365)

    @model_validator(mode="after")
    def storage_days_match_storage_request(self) -> MovingServices:
        if self.storage is True and self.storage_days is None:
            raise ValueError("storage_days is required when storage is requested")
        if self.storage is not True and self.storage_days is not None:
            raise ValueError("storage_days requires storage=true")
        return self


class JobSpecV1(ContractModel):
    job_id: UUID = Field(default_factory=uuid4)
    version: Literal["1.0"] = "1.0"
    intake_source: IntakeSource
    move_date: date | None = None
    date_flexible: bool | None = None
    origin: OriginDestinationAccess
    destination: OriginDestinationAccess
    bedroom_count: int | None = Field(default=None, ge=0, le=20)
    inventory: list[InventoryItem] = Field(default_factory=list)
    oversized_or_fragile_items: list[str] = Field(default_factory=list)
    services: MovingServices = Field(default_factory=MovingServices)
    insurance_preference: str | None = Field(default=None, min_length=1, max_length=120)
    confirmed: bool = False
    confirmed_at: datetime | None = None
    locked_version: Literal["1.0"] | None = None
    source_context: SourceContext = Field(default_factory=SourceContext)
    data_classification: DataClassification = DataClassification.SYNTHETIC

    @model_validator(mode="after")
    def confirmation_fields_are_consistent(self) -> JobSpecV1:
        if self.confirmed != (self.confirmed_at is not None):
            raise ValueError("confirmed and confirmed_at must be set together")
        if self.confirmed and self.locked_version != self.version:
            raise ValueError("confirmed JobSpec must lock its current version")
        if not self.confirmed and self.locked_version is not None:
            raise ValueError("locked_version requires confirmed=true")
        missing = self.missing_required_fields()
        if self.confirmed and missing:
            raise ValueError(f"confirmed JobSpec is missing required fields: {', '.join(missing)}")
        return self

    def missing_required_fields(self) -> list[str]:
        missing: list[str] = []
        scalar_fields = {
            "move_date": self.move_date,
            "date_flexible": self.date_flexible,
            "bedroom_count": self.bedroom_count,
            "insurance_preference": self.insurance_preference,
        }
        missing.extend(name for name, value in scalar_fields.items() if value is None)
        if not self.inventory:
            missing.append("inventory")
        for prefix, access in (("origin", self.origin), ("destination", self.destination)):
            for name in (
                "address_summary",
                "dwelling_type",
                "floors",
                "stairs",
                "elevator_access",
                "parking_distance_feet",
            ):
                if getattr(access, name) is None:
                    missing.append(f"{prefix}.{name}")
        for name in ("packing", "disassembly", "storage"):
            if getattr(self.services, name) is None:
                missing.append(f"services.{name}")
        return missing


class ProvenanceReference(ContractModel):
    source_type: ProvenanceType
    source_id: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=300)
    excerpt: str | None = Field(default=None, max_length=1000)


class FieldProvenance(ContractModel):
    field_path: str = Field(min_length=1, max_length=200)
    verification_status: VerificationStatus
    sources: list[ProvenanceReference] = Field(default_factory=list)


class Vendor(ContractModel):
    vendor_id: UUID
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    behavior_summary: str = Field(min_length=1, max_length=500)
    contact_label: str = Field(min_length=1, max_length=120)
    service_areas: list[str] = Field(min_length=1)
    data_classification: DataClassification = DataClassification.SYNTHETIC
    provenance: list[ProvenanceReference] = Field(default_factory=list)


class FeeLineItem(ContractModel):
    category: FeeCategory
    description: str = Field(min_length=1, max_length=300)
    amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    amount_status: AmountStatus = AmountStatus.KNOWN
    unit_rate: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    units: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    minimum_units: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    disclosed_upfront: bool = True
    mandatory: bool = False
    evidence_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def amount_matches_status(self) -> FeeLineItem:
        has_hourly_calculation = self.unit_rate is not None and (
            self.units is not None or self.minimum_units is not None
        )
        if (
            self.amount_status is AmountStatus.KNOWN
            and self.amount is None
            and not has_hourly_calculation
        ):
            raise ValueError("known fee amounts require an amount or calculable rate")
        if self.amount_status is AmountStatus.UNKNOWN and self.amount is not None:
            raise ValueError("unknown fee amounts must not contain an amount")
        return self


class TranscriptEvidence(ContractModel):
    evidence_id: UUID
    call_id: UUID
    excerpt: str = Field(min_length=1, max_length=1000)
    start_seconds: Decimal = Field(ge=0, decimal_places=2)
    end_seconds: Decimal = Field(ge=0, decimal_places=2)
    claim: str = Field(min_length=1, max_length=300)
    recording_url: HttpUrl
    data_classification: DataClassification = DataClassification.SYNTHETIC

    @model_validator(mode="after")
    def evidence_range_is_ordered(self) -> TranscriptEvidence:
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must not precede start_seconds")
        return self


class IntelligenceFinding(ContractModel):
    code: str = Field(pattern=r"^[a-z0-9_]+$")
    severity: FindingSeverity
    description: str = Field(min_length=1, max_length=500)
    deterministic: bool = True
    vendor_id: UUID | None = None
    quote_id: UUID | None = None
    fee_category: FeeCategory | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)


class QuoteV1(ContractModel):
    quote_id: UUID
    job_id: UUID
    vendor: Vendor
    job_spec_version: Literal["1.0"] = "1.0"
    fee_line_items: list[FeeLineItem] = Field(min_length=1)
    headline_total: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    original_total: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    negotiated_total: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    comparable_total: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: Literal["USD"] = "USD"
    deposit: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    binding_type: BindingType
    availability: str = Field(min_length=1, max_length=200)
    availability_status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    concessions: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    findings: list[IntelligenceFinding] = Field(default_factory=list)
    provisional_data: dict[str, Any] = Field(default_factory=dict)
    verified_data: dict[str, Any] = Field(default_factory=dict)
    verification_status: VerificationStatus
    transcript_evidence: list[TranscriptEvidence] = Field(default_factory=list)
    recording_url: HttpUrl
    provenance: list[ProvenanceReference] = Field(default_factory=list)
    manually_fabricated: bool = False
    data_classification: DataClassification = DataClassification.SYNTHETIC

    @model_validator(mode="after")
    def verified_quotes_require_safe_evidence(self) -> QuoteV1:
        if self.verification_status is VerificationStatus.VERIFIED:
            if self.manually_fabricated:
                raise ValueError("manually fabricated quotes cannot be verified")
            if not self.transcript_evidence:
                raise ValueError("verified quotes require transcript evidence")
            if self.comparable_total is None and self.negotiated_total is None:
                raise ValueError("verified quotes require a clear total")
        return self


class TranscriptQuoteFacts(ContractModel):
    fee_line_items: list[FeeLineItem] = Field(default_factory=list)
    spoken_total: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    binding_type: BindingType = BindingType.UNKNOWN
    availability: str = Field(default="Not established", min_length=1, max_length=200)
    availability_status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    addressed_fee_categories: list[FeeCategory] = Field(default_factory=list)
    evidence: list[TranscriptEvidence] = Field(default_factory=list)


class QuoteVerificationResult(ContractModel):
    verified_quote: QuoteV1
    findings: list[IntelligenceFinding] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)


class VerifiedCompetingQuote(ContractModel):
    quote: QuoteV1
    leverage_total: Decimal = Field(ge=0, decimal_places=2)
    evidence_ids: list[UUID] = Field(min_length=1)


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

        permitted_detail = {
            CallOutcomeType.ITEMIZED_QUOTE: "quote",
            CallOutcomeType.CALLBACK_COMMITMENT: "callback_at",
            CallOutcomeType.DOCUMENTED_DECLINE: "reason",
            CallOutcomeType.FAILED: "reason",
        }[self.type]
        populated_details = {
            name
            for name in ("quote", "callback_at", "reason")
            if getattr(self, name) is not None
        }
        unexpected_details = populated_details - {permitted_detail}
        if unexpected_details:
            raise ValueError(
                f"{self.type.value} only permits {permitted_detail}; "
                f"unexpected details: {', '.join(sorted(unexpected_details))}"
            )
        if self.callback_at is not None and (
            self.callback_at.tzinfo is None or self.callback_at.utcoffset() is None
        ):
            raise ValueError("callback_at must include a timezone")
        return self


class CallRecord(ContractModel):
    call_id: UUID
    job_id: UUID
    vendor: Vendor
    status: CallStatus
    started_at: datetime
    completed_at: datetime | None = None
    outcome: CallOutcome
    recording_url: HttpUrl | None = None

    @model_validator(mode="after")
    def terminal_call_is_internally_consistent(self) -> CallRecord:
        if self.status not in {CallStatus.COMPLETED, CallStatus.FAILED}:
            raise ValueError("canonical call records require terminal status")
        if self.completed_at is None:
            raise ValueError("terminal calls require completed_at")
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("started_at must include a timezone")
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("completed_at must include a timezone")
        expected_status = (
            CallStatus.FAILED
            if self.outcome.type is CallOutcomeType.FAILED
            else CallStatus.COMPLETED
        )
        if self.status is not expected_status:
            raise ValueError(
                f"{self.outcome.type.value} outcomes require status={expected_status.value}"
            )

        if (
            self.outcome.callback_at is not None
            and self.outcome.callback_at <= self.completed_at
        ):
            raise ValueError("callback_at must follow completed_at")

        if self.outcome.type is not CallOutcomeType.ITEMIZED_QUOTE:
            return self
        if self.recording_url is None:
            raise ValueError("itemized_quote calls require recording_url")

        quote = self.outcome.quote
        if quote is None:  # Defensive guard if the outcome was built without validation.
            raise ValueError("itemized_quote calls require quote")
        quote_recording = str(quote.recording_url)
        call_recording = str(self.recording_url)
        identity_matches = (
            quote.job_id == self.job_id
            and quote.vendor.vendor_id == self.vendor.vendor_id
            and quote_recording == call_recording
            and all(
                evidence.call_id == self.call_id
                and str(evidence.recording_url) == call_recording
                for evidence in quote.transcript_evidence
            )
        )
        if not identity_matches:
            raise ValueError(
                "itemized quote identity must match call job, vendor, evidence, and recording"
            )
        return self


class RecommendationRanking(ContractModel):
    rank: int = Field(ge=1)
    vendor: Vendor
    quote_id: UUID
    total: Decimal | None = Field(default=None, ge=0, decimal_places=2)
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
    cheapest_vendor_id: UUID | None = None
    best_value_vendor_id: UUID | None = None
    rankings: list[RecommendationRanking] = Field(min_length=1)
    evidence_ids: list[UUID] = Field(min_length=1)
    transcript_evidence: list[TranscriptEvidence] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    hidden_fee_findings: list[IntelligenceFinding] = Field(default_factory=list)


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
    source: Literal["synthetic_mock", "tavily"]


class DocumentParseResult(ContractModel):
    job_spec: JobSpecV1
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    fields_requiring_confirmation: list[str] = Field(default_factory=list)
    provenance: list[FieldProvenance] = Field(default_factory=list)

    @model_validator(mode="after")
    def missing_fields_match_job_spec(self) -> DocumentParseResult:
        actual = set(self.job_spec.missing_required_fields())
        if set(self.missing_fields) != actual:
            raise ValueError("missing_fields must exactly match the incomplete JobSpec fields")
        return self


class VendorSearchQuery(ContractModel):
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    service_type: str = Field(default="moving", min_length=1, max_length=100)
    radius_miles: int = Field(default=25, ge=1, le=250)


class ErrorDetail(ContractModel):
    code: str
    message: str


class ErrorResponse(ContractModel):
    error: ErrorDetail
