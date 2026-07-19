"""Safe merging of document facts into the same JobSpec contract used by voice intake."""

from __future__ import annotations

from copy import deepcopy

from services.api.app.contracts import (
    DocumentParseResult,
    FieldProvenance,
    IntakeSource,
    JobSpecV1,
)


def merge_document_with_voice(
    voice_spec: JobSpecV1,
    document_result: DocumentParseResult,
) -> DocumentParseResult:
    if voice_spec.confirmed:
        raise ValueError("a confirmed JobSpec cannot be merged")
    document_spec = document_result.job_spec
    payload = deepcopy(voice_spec.model_dump(mode="python"))
    document_payload = document_spec.model_dump(mode="python")

    for name in ("move_date", "date_flexible", "bedroom_count", "insurance_preference"):
        if payload[name] is None:
            payload[name] = document_payload[name]

    for location in ("origin", "destination"):
        for name in (
            "address_summary",
            "dwelling_type",
            "floors",
            "stairs",
            "elevator_access",
            "parking_distance_feet",
            "access_notes",
        ):
            if payload[location][name] is None:
                payload[location][name] = document_payload[location][name]

    for name in ("packing", "disassembly", "storage", "storage_days"):
        if payload["services"][name] is None:
            payload["services"][name] = document_payload["services"][name]

    if not payload["inventory"]:
        payload["inventory"] = document_payload["inventory"]
    payload["oversized_or_fragile_items"] = list(
        dict.fromkeys(
            [
                *payload["oversized_or_fragile_items"],
                *document_payload["oversized_or_fragile_items"],
            ]
        )
    )
    payload["intake_source"] = IntakeSource.MERGED
    payload["confirmed"] = False
    payload["confirmed_at"] = None
    payload["locked_version"] = None
    merged = JobSpecV1.model_validate(payload)
    missing = merged.missing_required_fields()
    provenance: list[FieldProvenance] = [
        *document_result.provenance,
    ]
    return DocumentParseResult(
        job_spec=merged,
        missing_fields=missing,
        warnings=document_result.warnings,
        fields_requiring_confirmation=sorted(
            set(document_result.fields_requiring_confirmation) | set(missing)
        ),
        provenance=provenance,
    )
