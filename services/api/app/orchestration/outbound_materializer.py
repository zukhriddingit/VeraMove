"""Deterministically convert authenticated outbound analysis into canonical outcomes."""

from __future__ import annotations

import json
import re
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
MAX_PROVIDER_CATEGORY_LENGTH = 100
UNKNOWN_PROVIDER_VALUES = frozenset(
    {
        "",
        "n/a",
        "na",
        "none",
        "not applicable",
        "not available",
        "not provided",
        "not specified",
        "not stated",
        "null",
        "unknown",
    }
)
PROVIDER_DECIMAL_PATTERN = re.compile(
    r"^\$?(?:\d+(?:\.\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?)$"
)
FEE_ITEM_FIELDS = frozenset(
    {
        "category",
        "description",
        "amount",
        "amount_status",
        "unit_rate",
        "units",
        "minimum_units",
        "disclosed_upfront",
        "mandatory",
    }
)


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
        return [FeeLineItem.model_validate(_normalize_fee_item(item)) for item in raw]
    except DomainConflict as exc:
        raise DomainConflict(f"fee_items_json contains an invalid fee: {exc}") from exc
    except ValidationError as exc:
        issues = sorted(
            {
                f"{'.'.join(str(part) for part in error['loc'])}:{error['type']}"
                for error in exc.errors(
                    include_url=False,
                    include_context=False,
                    include_input=False,
                )
            }
        )
        raise DomainConflict(
            "fee_items_json contains an invalid fee: " + ", ".join(issues[:8])
        ) from exc


def _normalize_fee_item(value: Any) -> dict[str, Any]:
    """Adapt bounded provider JSON without weakening the canonical fee contract."""

    if not isinstance(value, dict):
        raise DomainConflict("fee_items_json contains an invalid fee")
    normalized = {key: value[key] for key in FEE_ITEM_FIELDS if key in value}
    if "category" not in normalized and "fee_category" in value:
        normalized["category"] = value["fee_category"]
    if "description" not in normalized and "name" in value:
        normalized["description"] = value["name"]
    if "amount" not in normalized and "fee_amount" in value:
        normalized["amount"] = value["fee_amount"]
    normalized["category"] = _fee_category(
        normalized.get("category"),
        allow_missing=True,
    ).value
    if not isinstance(normalized.get("description"), str) or not normalized[
        "description"
    ].strip():
        normalized["description"] = (
            normalized["category"].replace("_", " ").capitalize() + " fee"
        )
    for field_name in ("amount", "unit_rate", "units", "minimum_units"):
        if field_name in normalized:
            normalized[field_name] = _provider_decimal(
                normalized[field_name],
                field_name,
            )
    for field_name in ("disclosed_upfront", "mandatory"):
        if normalized.get(field_name) is None:
            normalized.pop(field_name, None)
    has_amount = normalized.get("amount") is not None
    has_calculable_rate = normalized.get("unit_rate") is not None and (
        normalized.get("units") is not None
        or normalized.get("minimum_units") is not None
    )
    supplied_status = normalized.get("amount_status")
    parsed_status = (
        _amount_status(supplied_status)
        if supplied_status is not None
        else AmountStatus.UNKNOWN
    )
    if has_amount or has_calculable_rate:
        normalized["amount_status"] = AmountStatus.KNOWN.value
    elif parsed_status is AmountStatus.NOT_APPLICABLE:
        normalized["amount_status"] = AmountStatus.NOT_APPLICABLE.value
    else:
        normalized["amount_status"] = (
            AmountStatus.UNKNOWN.value
        )
    return normalized


def _fee_categories(value: Any) -> list[FeeCategory]:
    raw = _json_list(value, "addressed_fee_categories_json")
    if len(raw) > MAX_JSON_ITEMS:
        raise DomainConflict("addressed_fee_categories_json has too many items")
    return list(dict.fromkeys(_fee_category(item) for item in raw))


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
    conflicting_fields = {
        CallOutcomeType.ITEMIZED_QUOTE: {"callback_at", "outcome_reason"},
        CallOutcomeType.CALLBACK_COMMITMENT: {"outcome_reason"},
        CallOutcomeType.DOCUMENTED_DECLINE: {"callback_at"},
        CallOutcomeType.FAILED: {"callback_at"},
    }[outcome_type]
    populated_conflicts = {
        field_name
        for field_name in conflicting_fields
        if _provider_value_is_populated(data.get(field_name))
    }
    if populated_conflicts:
        raise DomainConflict(
            "Voice outcome contains mixed details: "
            + ", ".join(sorted(populated_conflicts))
        )


def _provider_value_is_populated(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _fee_category(value: Any, *, allow_missing: bool = False) -> FeeCategory:
    if value is None and allow_missing:
        return FeeCategory.OTHER
    if not isinstance(value, str):
        raise DomainConflict("fee category is invalid")
    stripped = value.strip()
    if not stripped or len(stripped) > MAX_PROVIDER_CATEGORY_LENGTH:
        raise DomainConflict("fee category is invalid")
    normalized = stripped.lower().replace("-", "_").replace(" ", "_")
    try:
        return FeeCategory(normalized)
    except ValueError:
        return FeeCategory.OTHER


def _amount_status(value: Any) -> AmountStatus:
    if not isinstance(value, str):
        raise DomainConflict("fee amount_status is invalid")
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "n/a": AmountStatus.NOT_APPLICABLE,
        "na": AmountStatus.NOT_APPLICABLE,
        "not_applicable": AmountStatus.NOT_APPLICABLE,
        "not_available": AmountStatus.UNKNOWN,
        "not_provided": AmountStatus.UNKNOWN,
        "not_specified": AmountStatus.UNKNOWN,
        "not_stated": AmountStatus.UNKNOWN,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return AmountStatus(normalized)
    except ValueError:
        raise DomainConflict("fee amount_status is invalid") from None


def _provider_decimal(value: Any, field_name: str) -> Decimal | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in UNKNOWN_PROVIDER_VALUES:
            return None
        if not PROVIDER_DECIMAL_PATTERN.fullmatch(stripped):
            raise DomainConflict(f"{field_name} is invalid")
        if stripped.startswith("$"):
            stripped = stripped[1:]
        value = stripped.replace(",", "")
    return _optional_decimal(value, field_name)


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
