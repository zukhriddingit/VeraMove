"""Generate deterministic ElevenLabs Data Collection and fee-probe assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "configs" / "moving.yaml"
DEFAULT_OUTPUT_ROOT = ROOT / "agents"
AGENT_CONFIG_VERSION = "2026-07-19.1"

GENERATED_ASSET_PATHS = (
    Path("intake/data-collection.json"),
    Path("negotiator/data-collection.json"),
    Path("negotiator/generated-fee-probes.md"),
)

INTAKE_FIELDS = (
    ("recording_consent", "boolean", "Whether the caller explicitly consented to recording."),
    (
        "summary_confirmed",
        "boolean",
        "Whether the caller agreed that the final readback was accurate; this never locks the job.",
    ),
    ("move_date", "string", "Requested move date in YYYY-MM-DD form."),
    ("date_flexible", "boolean", "Whether the requested move date is flexible."),
    (
        "origin_address_summary",
        "string",
        "Fictional role-play origin locality/address summary exactly as stated.",
    ),
    ("origin_dwelling_type", "string", "Origin dwelling type exactly as stated."),
    ("origin_floors", "integer", "Number of origin floors involved in the move."),
    ("origin_stairs", "integer", "Number of origin stair flights involved."),
    (
        "origin_elevator_access",
        "boolean",
        "Whether an elevator is available at the origin.",
    ),
    (
        "origin_parking_distance_feet",
        "integer",
        "Estimated origin parking-to-door carry distance in feet.",
    ),
    (
        "destination_address_summary",
        "string",
        "Fictional role-play destination locality/address summary exactly as stated.",
    ),
    (
        "destination_dwelling_type",
        "string",
        "Destination dwelling type exactly as stated.",
    ),
    (
        "destination_floors",
        "integer",
        "Number of destination floors involved in the move.",
    ),
    ("destination_stairs", "integer", "Number of destination stair flights involved."),
    (
        "destination_elevator_access",
        "boolean",
        "Whether an elevator is available at the destination.",
    ),
    (
        "destination_parking_distance_feet",
        "integer",
        "Estimated destination parking-to-door carry distance in feet.",
    ),
    ("bedroom_count", "integer", "Number of bedrooms included in the move."),
    (
        "inventory_json",
        "string",
        "JSON list of inventory items and quantities stated by the caller.",
    ),
    (
        "special_items_json",
        "string",
        "JSON string list of oversized, fragile, heavy, or high-value items.",
    ),
    ("packing", "boolean", "Whether packing service was requested."),
    ("disassembly", "boolean", "Whether disassembly service was requested."),
    ("storage", "boolean", "Whether storage service was requested."),
    (
        "storage_days",
        "integer",
        "Requested storage duration in days; collect only when storage is requested.",
    ),
    (
        "insurance_preference",
        "string",
        "Protection or insurance preference exactly as stated.",
    ),
)

OUTBOUND_FIELDS = (
    ("recording_consent", "boolean", "Whether the role-play vendor consented to recording."),
    (
        "outcome_type",
        "string",
        "Exactly itemized_quote, callback_commitment, documented_decline, or failed.",
    ),
    (
        "callback_at",
        "string",
        "Timezone-aware ISO 8601 callback time for callback_commitment; otherwise omit.",
    ),
    (
        "outcome_reason",
        "string",
        "Brief supported reason for documented_decline or failed; otherwise omit.",
    ),
    ("headline_total", "number", "Vendor's stated headline total, when provided."),
    ("deposit", "number", "Required deposit amount, when known."),
    (
        "original_total",
        "number",
        "Target vendor's original comparable total in negotiation mode.",
    ),
    (
        "negotiated_total",
        "number",
        "Target vendor's improved comparable total in negotiation mode, when agreed.",
    ),
    (
        "binding_type",
        "string",
        "Exact quote binding classification stated by the vendor.",
    ),
    (
        "availability_status",
        "string",
        "Exact normalized availability status stated by the vendor.",
    ),
    ("availability", "string", "Bounded availability detail exactly as stated."),
    (
        "fee_items_json",
        "string",
        "JSON list of fee category, description, amount/status, rate, units, disclosure, "
        "and mandatory values.",
    ),
    (
        "addressed_fee_categories_json",
        "string",
        "JSON string list of every configured fee category directly addressed in the call.",
    ),
    (
        "concessions_json",
        "string",
        "JSON string list of measurable concessions explicitly offered by the vendor.",
    ),
)

FEE_PROBE_TEXT = {
    "base_service": "Ask for the base moving-service charge and exactly what it includes.",
    "hourly_minimum": "Ask for the hourly rate, crew size, and minimum billable hours.",
    "travel": "Ask about travel time, dispatch, mileage, or trip charges.",
    "fuel": "Ask whether a fuel surcharge applies and how it is calculated.",
    "stairs": "Ask for every origin and destination stair charge.",
    "elevator": "Ask whether elevator access, reservations, or wait time add a charge.",
    "long_carry": "Ask for the carry-distance threshold, rate, and expected long-carry charge.",
    "packing": "Ask for labor charges for requested packing service.",
    "materials": "Ask for box, wrap, tape, padding, and other material charges.",
    "disassembly": "Ask for furniture disassembly and reassembly charges.",
    "storage": "Ask for storage, handling, access, and minimum-duration charges.",
    "insurance": "Ask about included valuation and optional protection charges.",
    "tax": "Ask which taxes apply and whether they are included in the stated total.",
    "deposit": "Ask for the deposit amount, refundability, due date, and payment conditions.",
}


def _collection_document(role: str, fields: tuple[tuple[str, str, str], ...]) -> str:
    payload = {
        "agent_config_version": AGENT_CONFIG_VERSION,
        "fields": [
            {"identifier": identifier, "type": field_type, "description": description}
            for identifier, field_type, description in fields
        ],
        "provider": "elevenlabs",
        "role": role,
        "schema_type": "post_call_data_collection",
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _fee_probe_document(categories: list[str]) -> str:
    lines = [
        "# Generated mandatory fee probes",
        "",
        "<!-- Generated by scripts/generate_agent_assets.py from configs/moving.yaml. -->",
        "<!-- Paste this fragment into the outbound prompt in the ElevenLabs dashboard. -->",
        "",
    ]
    for category in categories:
        probe = FEE_PROBE_TEXT.get(
            category,
            f"Ask whether {category.replace('_', ' ')} creates a charge and how it is calculated.",
        )
        lines.append(f"- `{category}`: {probe}")
    return "\n".join(lines) + "\n"


def render_agent_assets(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[Path, str]:
    """Return every generated asset without reading credentials or calling a provider."""

    config: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    mandatory_categories = config.get("mandatory_fee_questions")
    fee_categories = config.get("fee_categories")
    if not isinstance(mandatory_categories, list) or not all(
        isinstance(value, str) for value in mandatory_categories
    ):
        raise ValueError("mandatory_fee_questions must be a list of strings")
    if len(mandatory_categories) != len(set(mandatory_categories)):
        raise ValueError("mandatory_fee_questions must not contain duplicates")
    if not isinstance(fee_categories, list) or not set(mandatory_categories) <= set(fee_categories):
        raise ValueError("every mandatory fee question must be a configured fee category")

    return {
        GENERATED_ASSET_PATHS[0]: _collection_document("intake", INTAKE_FIELDS),
        GENERATED_ASSET_PATHS[1]: _collection_document("outbound_negotiator", OUTBOUND_FIELDS),
        GENERATED_ASSET_PATHS[2]: _fee_probe_document(mandatory_categories),
    }


def generate_agent_assets(
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> list[Path]:
    """Write deterministic assets beneath ``output_root`` and return their paths."""

    rendered = render_agent_assets(config_path)
    written: list[Path] = []
    for relative_path in GENERATED_ASSET_PATHS:
        target = output_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered[relative_path], encoding="utf-8")
        written.append(target)
    return written


def check_agent_assets(
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> list[Path]:
    """Return missing or stale generated assets without modifying the filesystem."""

    rendered = render_agent_assets(config_path)
    stale: list[Path] = []
    for relative_path in GENERATED_ASSET_PATHS:
        target = output_root / relative_path
        if not target.exists() or target.read_text(encoding="utf-8") != rendered[relative_path]:
            stale.append(target)
    return stale


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if committed assets are stale.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    if args.check:
        stale = check_agent_assets(output_root=args.output_root, config_path=args.config)
        if stale:
            for path in stale:
                print(f"Stale generated agent asset: {path}")
            return 1
        print("Agent assets are up to date.")
        return 0

    written = generate_agent_assets(output_root=args.output_root, config_path=args.config)
    for path in written:
        print(f"Generated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
