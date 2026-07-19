"""Deterministically convert authenticated outbound analysis into canonical outcomes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import HttpUrl, ValidationError

from services.api.app.contracts import (
    AmountStatus,
    AvailabilityStatus,
    BindingType,
    CallOutcome,
    CallOutcomeType,
    CallStatus,
    DataClassification,
    FeeCategory,
    FeeLineItem,
    QuoteV1,
    TranscriptQuoteFacts,
    VerificationStatus,
)
from services.api.app.core.errors import DomainConflict
from services.api.app.integrations.elevenlabs.models import VerifiedPostCallTranscription
from services.api.app.orchestration.evidence import (
    EvidenceClaim,
    build_transcript_evidence,
)
from services.api.app.orchestration.models import CallAttempt
from services.api.app.orchestration.providers import QuoteVerificationGateway

MAX_JSON_ITEMS = 40
MAX_CONCESSIONS = 20


@dataclass(frozen=True, slots=True)
class MaterializedOutboundOutcome:
    """Canonical outcome plus the optional audio capability used by its call."""

    outcome: CallOutcome
    recording_url: HttpUrl | None
    provider_version_id: str | None


def materialize_outbound_event(
    *,
    event: VerifiedPostCallTranscription,
    attempt: CallAttempt,
    recording_url: HttpUrl,
    verifier: QuoteVerificationGateway,
    required_fee_categories: set[FeeCategory],
) -> MaterializedOutboundOutcome:
    """Cross-check correlation and create only evidence-supported canonical facts."""

    _validate_correlation(event, attempt)
    data = event.collected_data
    outcome_type = _outcome_type(data.get("outcome_type"))
    _validate_outcome_data_exclusive(outcome_type, data)
    audio_url = (
        recording_url
        if event.has_audio and data.get("recording_consent") is True
        else None
    )
    if outcome_type is CallOutcomeType.ITEMIZED_QUOTE:
        if data.get("recording_consent") is not True or audio_url is None:
            raise DomainConflict("Itemized quote requires consent and saved audio")
        outcome = CallOutcome(
            type=outcome_type,
            quote=_materialize_quote(
                event=event,
                attempt=attempt,
                recording_url=audio_url,
                verifier=verifier,
                required_fee_categories=required_fee_categories,
            ),
        )
    elif outcome_type is CallOutcomeType.CALLBACK_COMMITMENT:
        callback_at = _aware_datetime(data.get("callback_at"), "callback_at")
        outcome = CallOutcome(type=outcome_type, callback_at=callback_at)
    else:
        reason = _bounded_text(data.get("outcome_reason"), "outcome_reason", 500)
        outcome = CallOutcome(type=outcome_type, reason=reason)
    return MaterializedOutboundOutcome(
        outcome=outcome,
        recording_url=audio_url,
        provider_version_id=event.version_id,
    )


def _validate_correlation(
    event: VerifiedPostCallTranscription,
    attempt: CallAttempt,
) -> None:
    if event.provider_status != "done" or event.call_status is not CallStatus.COMPLETED:
        raise DomainConflict("Voice completion event is not in a supported done state")
    variables = event.dynamic_variables
    mismatches = {
        "agent": event.agent_id != attempt.expected_agent_id,
        "conversation": (
            attempt.reference is None or event.conversation_id != attempt.reference.conversation_id
        ),
        "call": variables.call_id != attempt.call_id,
        "job": variables.job_id != attempt.job_id,
        "vendor": variables.vendor_id != attempt.vendor.vendor_id,
        "mode": variables.call_mode != attempt.call_mode,
        "version": variables.job_spec_version != attempt.job_spec_version,
        "agent_config": variables.agent_config_version != attempt.agent_config_version,
        "snapshot": variables.job_spec_sha256 != attempt.job_spec_sha256,
    }
    failed = [name for name, mismatch in mismatches.items() if mismatch]
    if failed:
        raise DomainConflict("Voice event correlation mismatch: " + ", ".join(failed))


def _materialize_quote(
    *,
    event: VerifiedPostCallTranscription,
    attempt: CallAttempt,
    recording_url: HttpUrl,
    verifier: QuoteVerificationGateway,
    required_fee_categories: set[FeeCategory],
) -> QuoteV1:
    data = event.collected_data
    fee_items = _fee_items(data.get("fee_items_json"))
    addressed = _fee_categories(data.get("addressed_fee_categories_json"))
    concessions = _string_list(data.get("concessions_json"), "concessions_json")
    spoken_total = _first_decimal(
        data,
        "negotiated_total",
        "original_total",
        "headline_total",
    )
    binding = _enum_value(BindingType, data.get("binding_type"), "binding_type")
    availability_status = _enum_value(
        AvailabilityStatus,
        data.get("availability_status"),
        "availability_status",
    )
    availability = _bounded_text(
        data.get("availability") or "Not established",
        "availability",
        200,
    )
    claims: list[EvidenceClaim] = []
    for index, fee in enumerate(fee_items):
        amount = _fee_amount(fee)
        claims.append(
            EvidenceClaim(
                claim=f"fee:{fee.category.value}:{index}",
                phrases=(_category_phrase(fee.category),),
                amount=amount,
            )
        )
    if spoken_total is not None:
        claims.append(EvidenceClaim("quote_total", ("total",), spoken_total))
    if binding is not BindingType.UNKNOWN:
        claims.append(
            EvidenceClaim(
                "binding_status",
                ("non binding",) if binding is BindingType.NON_BINDING else ("binding",),
            )
        )
    if availability_status is not AvailabilityStatus.UNKNOWN:
        claims.append(
            EvidenceClaim(
                "availability_status",
                ("unavailable",)
                if availability_status is AvailabilityStatus.UNAVAILABLE
                else ("available",),
            )
        )
    evidence = build_transcript_evidence(
        call_id=attempt.call_id,
        recording_url=recording_url,
        transcript_turns=event.transcript_turns,
        claims=claims,
        data_classification=DataClassification.ROLE_PLAY,
    )
    evidence_by_claim = {item.claim: item.evidence_id for item in evidence}
    supported_fees = [
        fee.model_copy(
            update={
                "evidence_ids": [evidence_by_claim[f"fee:{fee.category.value}:{index}"]]
                if f"fee:{fee.category.value}:{index}" in evidence_by_claim
                else []
            },
            deep=True,
        )
        for index, fee in enumerate(fee_items)
    ]
    quote_id = uuid5(NAMESPACE_URL, f"veramove-live-quote:{attempt.call_id}")
    provisional = QuoteV1(
        quote_id=quote_id,
        job_id=attempt.job_id,
        vendor=attempt.vendor,
        job_spec_version=attempt.job_spec_version,
        fee_line_items=fee_items,
        headline_total=_optional_decimal(data.get("headline_total"), "headline_total"),
        original_total=_optional_decimal(data.get("original_total"), "original_total"),
        negotiated_total=_optional_decimal(
            data.get("negotiated_total"),
            "negotiated_total",
        ),
        comparable_total=None,
        deposit=_optional_decimal(data.get("deposit"), "deposit"),
        binding_type=binding,
        availability=availability,
        availability_status=availability_status,
        concessions=concessions,
        provisional_data={
            "source": "elevenlabs_data_collection",
            "call_mode": attempt.call_mode,
        },
        verified_data={},
        verification_status=VerificationStatus.PROVISIONAL,
        transcript_evidence=[],
        recording_url=recording_url,
        manually_fabricated=False,
        data_classification=DataClassification.ROLE_PLAY,
    )
    facts = TranscriptQuoteFacts(
        fee_line_items=supported_fees,
        spoken_total=spoken_total,
        binding_type=binding,
        availability=availability,
        availability_status=availability_status,
        addressed_fee_categories=addressed,
        evidence=evidence,
    )
    return verifier.verify(
        provisional,
        facts,
        required_fee_categories,
    ).verified_quote


def _fee_items(value: Any) -> list[FeeLineItem]:
    raw = _json_list(value, "fee_items_json")
    if not raw or len(raw) > MAX_JSON_ITEMS:
        raise DomainConflict("fee_items_json must contain 1 to 40 items")
    try:
        return [FeeLineItem.model_validate(item) for item in raw]
    except ValidationError as exc:
        raise DomainConflict("fee_items_json contains an invalid fee") from exc


def _fee_categories(value: Any) -> list[FeeCategory]:
    raw = _json_list(value, "addressed_fee_categories_json")
    if len(raw) > MAX_JSON_ITEMS:
        raise DomainConflict("addressed_fee_categories_json has too many items")
    try:
        return list(dict.fromkeys(FeeCategory(item) for item in raw))
    except (TypeError, ValueError):
        raise DomainConflict("addressed_fee_categories_json is invalid") from None


def _string_list(value: Any, field_name: str) -> list[str]:
    raw = _json_list(value, field_name)
    if len(raw) > MAX_CONCESSIONS:
        raise DomainConflict(f"{field_name} has too many items")
    if any(
        not isinstance(item, str) or not item.strip() or len(item.strip()) > 200 for item in raw
    ):
        raise DomainConflict(f"{field_name} is invalid")
    return list(dict.fromkeys(item.strip() for item in raw))


def _json_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, str) or len(value) > 20_000:
        raise DomainConflict(f"{field_name} must be bounded JSON text")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise DomainConflict(f"{field_name} must be valid JSON") from exc
    if not isinstance(parsed, list):
        raise DomainConflict(f"{field_name} must contain a JSON list")
    return parsed


def _outcome_type(value: Any) -> CallOutcomeType:
    try:
        return CallOutcomeType(value)
    except (TypeError, ValueError):
        raise DomainConflict("Voice outcome_type is invalid") from None


def _validate_outcome_data_exclusive(
    outcome_type: CallOutcomeType,
    data: dict[str, Any],
) -> None:
    quote_fields = {
        "headline_total",
        "deposit",
        "original_total",
        "negotiated_total",
        "binding_type",
        "availability_status",
        "availability",
        "fee_items_json",
        "addressed_fee_categories_json",
        "concessions_json",
    }
    allowed_details = {
        CallOutcomeType.ITEMIZED_QUOTE: quote_fields,
        CallOutcomeType.CALLBACK_COMMITMENT: {"callback_at"},
        CallOutcomeType.DOCUMENTED_DECLINE: {"outcome_reason"},
        CallOutcomeType.FAILED: {"outcome_reason"},
    }[outcome_type]
    populated_details = {
        key for key in quote_fields | {"callback_at", "outcome_reason"} if data.get(key) is not None
    }
    unexpected = populated_details - allowed_details
    if unexpected:
        raise DomainConflict(
            "Voice outcome contains mixed details: " + ", ".join(sorted(unexpected))
        )


def _aware_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise DomainConflict(f"{field_name} must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise DomainConflict(f"{field_name} must be a timezone-aware timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DomainConflict(f"{field_name} must be a timezone-aware timestamp")
    return parsed


def _bounded_text(value: Any, field_name: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_length:
        raise DomainConflict(f"{field_name} is missing or invalid")
    return value.strip()


def _optional_decimal(value: Any, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise DomainConflict(f"{field_name} is invalid")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise DomainConflict(f"{field_name} is invalid") from None
    if not parsed.is_finite() or parsed < 0:
        raise DomainConflict(f"{field_name} is invalid")
    return parsed.quantize(Decimal("0.01"))


def _first_decimal(data: dict[str, Any], *field_names: str) -> Decimal | None:
    for field_name in field_names:
        value = _optional_decimal(data.get(field_name), field_name)
        if value is not None:
            return value
    return None


def _enum_value(enum_type: type, value: Any, field_name: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        raise DomainConflict(f"{field_name} is invalid") from None


def _fee_amount(item: FeeLineItem) -> Decimal | None:
    if item.amount_status is not AmountStatus.KNOWN:
        return None
    if item.amount is not None:
        return item.amount
    if item.unit_rate is None:
        return None
    units = max(item.units or Decimal("0"), item.minimum_units or Decimal("0"))
    return (item.unit_rate * units).quantize(Decimal("0.01"))


def _category_phrase(category: FeeCategory) -> str:
    aliases = {
        FeeCategory.BASE_SERVICE: "base service",
        FeeCategory.HOURLY_MINIMUM: "hourly minimum",
        FeeCategory.LONG_CARRY: "long carry",
    }
    return aliases.get(category, category.value.replace("_", " "))
