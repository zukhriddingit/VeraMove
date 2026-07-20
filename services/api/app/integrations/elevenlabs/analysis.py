"""Allowlisted parsing for probabilistic ElevenLabs post-call analysis."""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from services.api.app.contracts import CallStatus
from services.api.app.core.errors import WebhookPayloadError
from services.api.app.integrations.elevenlabs.models import (
    ElevenLabsDynamicVariables,
    ElevenLabsTranscriptTurn,
    PrimitiveValue,
    VerifiedCallInitiationFailure,
    VerifiedPostCallTranscription,
)

MAX_TRANSCRIPT_TURNS = 500
MAX_COLLECTION_ITEMS = 40
MAX_COLLECTION_STRING_LENGTH = 20_000

INTAKE_COLLECTION_FIELDS = frozenset(
    {
        "recording_consent",
        "summary_confirmed",
        "move_date",
        "date_flexible",
        "origin_address_summary",
        "origin_dwelling_type",
        "origin_floors",
        "origin_stairs",
        "origin_elevator_access",
        "origin_parking_distance_feet",
        "destination_address_summary",
        "destination_dwelling_type",
        "destination_floors",
        "destination_stairs",
        "destination_elevator_access",
        "destination_parking_distance_feet",
        "bedroom_count",
        "inventory_json",
        "special_items_json",
        "packing",
        "disassembly",
        "storage",
        "storage_days",
        "insurance_preference",
    }
)
OUTBOUND_COLLECTION_FIELDS = frozenset(
    {
        "recording_consent",
        "outcome_type",
        "callback_at",
        "outcome_reason",
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
)
ALLOWED_COLLECTION_FIELDS = INTAKE_COLLECTION_FIELDS | OUTBOUND_COLLECTION_FIELDS


def _text(value: Any, field_name: str, *, max_length: int = 200) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WebhookPayloadError(f"ElevenLabs {field_name} is missing or invalid")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise WebhookPayloadError(f"ElevenLabs {field_name} is too long")
    return normalized


def _optional_text(value: Any, field_name: str, *, max_length: int = 200) -> str | None:
    if value is None:
        return None
    return _text(value, field_name, max_length=max_length)


def _optional_uuid(value: Any, field_name: str) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise WebhookPayloadError(f"ElevenLabs {field_name} is invalid") from None


def parse_dynamic_variables(data: dict[str, Any]) -> ElevenLabsDynamicVariables:
    initiation = data.get("conversation_initiation_client_data")
    initiation_data = initiation if isinstance(initiation, dict) else {}
    raw_variables = initiation_data.get("dynamic_variables")
    variables = raw_variables if isinstance(raw_variables, dict) else {}
    payload: dict[str, Any] = {
        "job_id": _optional_uuid(variables.get("job_id"), "job_id"),
        "call_id": _optional_uuid(variables.get("call_id"), "call_id"),
        "intake_session_id": _optional_uuid(
            variables.get("intake_session_id"),
            "intake_session_id",
        ),
        "vendor_id": _optional_uuid(variables.get("vendor_id"), "vendor_id"),
        "call_mode": variables.get("call_mode"),
        "job_spec_version": variables.get("job_spec_version"),
        "agent_config_version": variables.get("agent_config_version"),
        "job_spec_sha256": variables.get("job_spec_sha256"),
    }
    try:
        return ElevenLabsDynamicVariables.model_validate(payload)
    except ValidationError as exc:
        raise WebhookPayloadError("ElevenLabs dynamic variables are invalid") from exc


def _normalize_primitive(value: Any) -> PrimitiveValue:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        if len(value) > MAX_COLLECTION_STRING_LENGTH:
            raise WebhookPayloadError("ElevenLabs collected value is too large")
        normalized = value.strip()
        return normalized or None
    raise WebhookPayloadError("ElevenLabs collected value has an unsupported type")


def _collection_entries(analysis: dict[str, Any]) -> list[tuple[str, Any]]:
    entries: list[tuple[str, Any]] = []
    mapping = analysis.get("data_collection_results")
    if isinstance(mapping, dict):
        for key, raw_entry in mapping.items():
            if not isinstance(key, str) or not isinstance(raw_entry, dict):
                raise WebhookPayloadError("ElevenLabs Data Collection map is invalid")
            identifier = raw_entry.get("data_collection_id", key)
            entries.append((str(identifier), raw_entry.get("value")))
    listed = analysis.get("data_collection_results_list")
    if isinstance(listed, list):
        for raw_entry in listed:
            if not isinstance(raw_entry, dict):
                raise WebhookPayloadError("ElevenLabs Data Collection list is invalid")
            identifier = raw_entry.get("data_collection_id")
            if not isinstance(identifier, str):
                raise WebhookPayloadError("ElevenLabs Data Collection identifier is invalid")
            entries.append((identifier, raw_entry.get("value")))
    if len({identifier for identifier, _value in entries}) > MAX_COLLECTION_ITEMS:
        raise WebhookPayloadError("ElevenLabs Data Collection has too many items")
    return entries


def normalize_collected_data(data: dict[str, Any]) -> dict[str, PrimitiveValue]:
    raw_analysis = data.get("analysis")
    analysis = raw_analysis if isinstance(raw_analysis, dict) else {}
    normalized: dict[str, PrimitiveValue] = {}
    for raw_identifier, raw_value in _collection_entries(analysis):
        identifier = _text(
            raw_identifier,
            "Data Collection identifier",
            max_length=120,
        )
        if identifier not in ALLOWED_COLLECTION_FIELDS:
            continue
        value = _normalize_primitive(raw_value)
        if identifier in normalized and normalized[identifier] != value:
            raise WebhookPayloadError(
                "ElevenLabs Data Collection contains a conflicting duplicate identifier"
            )
        normalized[identifier] = value
    return normalized


def parse_transcript_turns(data: dict[str, Any]) -> tuple[ElevenLabsTranscriptTurn, ...]:
    raw_transcript = data.get("transcript")
    if raw_transcript is None:
        return ()
    if not isinstance(raw_transcript, list):
        raise WebhookPayloadError("ElevenLabs transcript is invalid")
    if len(raw_transcript) > MAX_TRANSCRIPT_TURNS:
        raise WebhookPayloadError("ElevenLabs transcript has too many turns")
    turns: list[ElevenLabsTranscriptTurn] = []
    for raw_turn in raw_transcript:
        if not isinstance(raw_turn, dict):
            raise WebhookPayloadError("ElevenLabs transcript turn is invalid")
        message = raw_turn.get("message")
        if message is not None and not isinstance(message, str):
            raise WebhookPayloadError("ElevenLabs transcript message is invalid")
        if isinstance(message, str) and len(message) > 2_000:
            raise WebhookPayloadError("ElevenLabs transcript message is too long")
        try:
            timestamp = Decimal(str(raw_turn.get("time_in_call_secs", 0)))
        except (InvalidOperation, TypeError, ValueError):
            raise WebhookPayloadError("ElevenLabs transcript timestamp is invalid") from None
        try:
            turns.append(
                ElevenLabsTranscriptTurn(
                    role=_text(raw_turn.get("role"), "transcript role", max_length=40),
                    message=message,
                    time_in_call_secs=timestamp,
                )
            )
        except ValidationError as exc:
            raise WebhookPayloadError("ElevenLabs transcript turn is invalid") from exc
    return tuple(turns)


def _idempotency_key(event_type: str, conversation_id: str, timestamp: datetime) -> str:
    material = f"{event_type}:{conversation_id}:{timestamp.isoformat()}"
    return hashlib.sha256(material.encode()).hexdigest()


def parse_post_call_transcription(
    payload: dict[str, Any],
    event_timestamp: datetime,
) -> VerifiedPostCallTranscription:
    raw_data = payload.get("data")
    if not isinstance(raw_data, dict):
        raise WebhookPayloadError("ElevenLabs post-call data is invalid")
    agent_id = _text(raw_data.get("agent_id"), "agent_id")
    conversation_id = _text(raw_data.get("conversation_id"), "conversation_id")
    provider_status = _text(raw_data.get("status"), "status", max_length=80)
    call_status = {
        "done": CallStatus.COMPLETED,
        "failed": CallStatus.FAILED,
    }.get(provider_status)
    try:
        return VerifiedPostCallTranscription(
            idempotency_key=_idempotency_key(
                "post_call_transcription",
                conversation_id,
                event_timestamp,
            ),
            event_timestamp=event_timestamp,
            agent_id=agent_id,
            conversation_id=conversation_id,
            provider_status=provider_status,
            call_status=call_status,
            version_id=_optional_text(raw_data.get("version_id"), "version_id"),
            environment=_optional_text(
                raw_data.get("environment"),
                "environment",
                max_length=80,
            ),
            has_audio=raw_data.get("has_audio") is True,
            dynamic_variables=parse_dynamic_variables(raw_data),
            collected_data=normalize_collected_data(raw_data),
            transcript_turns=parse_transcript_turns(raw_data),
        )
    except ValidationError as exc:
        raise WebhookPayloadError("ElevenLabs post-call fields are invalid") from exc


def parse_call_initiation_failure(
    payload: dict[str, Any],
    event_timestamp: datetime,
) -> VerifiedCallInitiationFailure:
    raw_data = payload.get("data")
    if not isinstance(raw_data, dict):
        raise WebhookPayloadError("ElevenLabs initiation failure data is invalid")
    agent_id = _text(raw_data.get("agent_id"), "agent_id")
    conversation_id = _text(raw_data.get("conversation_id"), "conversation_id")
    failure_reason = _text(
        raw_data.get("failure_reason"),
        "failure_reason",
        max_length=80,
    )
    try:
        return VerifiedCallInitiationFailure(
            idempotency_key=_idempotency_key(
                "call_initiation_failure",
                conversation_id,
                event_timestamp,
            ),
            event_timestamp=event_timestamp,
            agent_id=agent_id,
            conversation_id=conversation_id,
            failure_reason=failure_reason,
        )
    except ValidationError as exc:
        raise WebhookPayloadError("ElevenLabs initiation failure fields are invalid") from exc
