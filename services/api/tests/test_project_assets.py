"""Structural checks for configuration, fixtures, and migration assets."""

import json
import re
from pathlib import Path

import pytest
import yaml

from scripts.generate_agent_assets import elevenlabs_data_collection

ROOT = Path(__file__).resolve().parents[3]


def test_moving_config_contains_required_vertical_rules():
    config = yaml.safe_load((ROOT / "configs/moving.yaml").read_text(encoding="utf-8"))
    assert config["red_flag_rules"]["below_comparison_median_percent"] == 30
    assert set(config["required_call_outcomes"]) == {
        "itemized_quote",
        "callback_commitment",
        "documented_decline",
        "failed",
    }
    assert "long_carry" in config["fee_categories"]
    assert "tax" in config["fee_categories"]
    assert len(config["vendor_policy_cards"]) == 3
    assert config["document_intake"]["accepted_mime_types"] == [
        "application/pdf",
        "image/png",
        "image/jpeg",
    ]
    assert len(config["honesty_constraints"]) >= 4


def test_migration_has_all_tables_indexes_jsonb_and_idempotency():
    path = ROOT / "supabase/migrations/202607180001_initial_schema.sql"
    sql = path.read_text(encoding="utf-8").lower()
    for table in (
        "jobs",
        "vendors",
        "calls",
        "quotes",
        "transcript_evidence",
        "recommendations",
        "event_log",
    ):
        assert f"create table if not exists {table}" in sql
    assert "idempotency_key text not null unique" in sql
    assert "jsonb" in sql
    assert "verification_status" in sql
    assert "provenance" in sql
    assert "data_classification" in sql
    assert "manually_fabricated" in sql
    assert "jobs_lock_consistency" in sql
    assert "create index if not exists" in sql


def test_all_demo_json_is_explicitly_synthetic_or_covered_by_disclosure():
    readme = (ROOT / "data/demo/README.md").read_text(encoding="utf-8").lower()
    assert "every file" in readme and "synthetic" in readme
    policy_cards = json.loads(
        (ROOT / "data/demo/vendor_policy_cards.json").read_text(encoding="utf-8")
    )
    assert all(card["synthetic"] is True for card in policy_cards)


def test_public_dataset_contains_every_required_artifact():
    required = {
        "job_specs.jsonl",
        "vendor_policies.json",
        "quotes.jsonl",
        "transcript_evidence.jsonl",
        "call_outcomes.jsonl",
        "recommendations.jsonl",
        "eval_results.csv",
        "README.md",
    }
    assert required <= {path.name for path in (ROOT / "data/demo").iterdir()}


def test_evaluation_covers_required_mock_outcomes():
    payload = json.loads((ROOT / "evals/mock_workflow_cases.json").read_text(encoding="utf-8"))
    names = {case["name"] for case in payload["cases"]}
    assert names == {
        "three_vendor_calls",
        "negotiated_quote_added",
        "measurable_improvement",
        "hidden_fee_detection",
        "evidence_backed_ranking",
    }


def test_exactly_two_professional_voice_agent_roles_exist():
    role_directories = {
        path.name
        for path in (ROOT / "agents").iterdir()
        if path.is_dir() and not path.name.startswith("__")
    }
    assert role_directories == {"intake", "negotiator"}


def test_voice_agent_assets_are_professional_and_machine_readable():
    intake_prompt = (ROOT / "agents/intake/prompt.md").read_text(encoding="utf-8")
    negotiator_prompt = (ROOT / "agents/negotiator/prompt.md").read_text(encoding="utf-8")
    intake_config = yaml.safe_load(
        (ROOT / "agents/intake/agent.yaml").read_text(encoding="utf-8"),
    )
    negotiator_config = yaml.safe_load(
        (ROOT / "agents/negotiator/agent.yaml").read_text(encoding="utf-8"),
    )
    tools = yaml.safe_load((ROOT / "agents/tools.yaml").read_text(encoding="utf-8"))

    assert intake_config["agent_config_version"] == negotiator_config["agent_config_version"]
    assert intake_config["agent_config_version"] == "2026-07-19.1"
    assert intake_config["agent"]["display_name"] == "VeraMove Intake"
    assert negotiator_config["agent"]["display_name"] == "VeraMove Outbound Negotiator"
    assert intake_config["agent"]["data_collection_file"] == "data-collection.json"
    assert negotiator_config["agent"]["data_collection_file"] == "data-collection.json"
    assert negotiator_config["agent"]["fee_probes_file"] == "generated-fee-probes.md"
    assert intake_config["agent"]["dashboard_sync"] == "manual"
    assert negotiator_config["agent"]["dashboard_sync"] == "manual"
    for config in (intake_config, negotiator_config):
        agent = config["agent"]
        assert agent["backend_boundaries_file"] == "../tools.yaml"
        assert agent["provider_tool_ids"] == []
        assert agent["provider_tools_status"] == "omitted_until_reviewed_ids_exist"
        assert agent["provider_version"] == {
            "version_description": "VeraMove 2026-07-19.1",
            "capture_after_save": ["version_id", "branch_id"],
            "provider_ids_committed": False,
        }

    intake_variables = {
        variable["name"] for variable in intake_config["agent"]["dynamic_variables"]
    }
    assert intake_variables == {"job_id", "intake_session_id", "agent_config_version"}
    outbound_variables = {
        variable["name"] for variable in negotiator_config["agent"]["dynamic_variables"]
    }
    assert outbound_variables == {
        "job_id",
        "call_id",
        "vendor_id",
        "vendor_name",
        "job_spec_version",
        "job_spec_json",
        "call_mode",
        "agent_config_version",
        "verified_competitor_quote_id",
        "verified_competitor_total",
        "verified_competitor_evidence_json",
        "negotiation_objective",
    }
    assert all(
        variable["type"] == "string"
        for variable in (
            intake_config["agent"]["dynamic_variables"]
            + negotiator_config["agent"]["dynamic_variables"]
        )
    )
    assert {f"{{{{{name}}}}}" for name in intake_variables} <= set(
        re.findall(r"\{\{[a-z_]+\}\}", intake_prompt)
    )
    assert {f"{{{{{name}}}}}" for name in outbound_variables} <= set(
        re.findall(r"\{\{[a-z_]+\}\}", negotiator_prompt)
    )

    for prompt in (intake_prompt.lower(), negotiator_prompt.lower()):
        for phrase in (
            "ai assistant",
            "may be recorded",
            "do you consent",
            "asks to stop",
            "never book",
        ):
            assert phrase in prompt
    assert "read the complete move summary" in intake_prompt.lower()
    assert "does not confirm or lock" in intake_prompt.lower()
    assert "call_mode=quote" in negotiator_prompt
    assert "call_mode=negotiation" in negotiator_prompt
    assert "get_verified_competing_quote" in negotiator_prompt
    assert "verified different-vendor" in negotiator_prompt.lower()
    assert "synthetic role-play" in negotiator_prompt.lower()
    assert all(
        outcome in negotiator_prompt
        for outcome in (
            "itemized_quote",
            "callback_commitment",
            "documented_decline",
            "failed",
        )
    )

    assert negotiator_config["agent"]["structured_output"] == "CallOutcome"
    assert [tool["name"] for tool in tools["tools"]] == [
        "save_quote",
        "save_call_outcome",
        "get_verified_competing_quote",
        "request_callback",
    ]
    assert all("required" in tool and "properties" in tool for tool in tools["tools"])
    serialized = "\n".join(
        (intake_prompt, negotiator_prompt, yaml.safe_dump(intake_config), yaml.safe_dump(tools)),
    ).lower()
    for unsafe_key in ("xi-api-key", "sk-", "phone_number", "@example.com", "replace_me"):
        assert unsafe_key not in serialized
    assert re.search(r"\+[1-9]\d{7,14}\b", serialized) is None


def test_voice_data_collection_assets_match_the_approved_contract():
    intake = json.loads((ROOT / "agents/intake/data-collection.json").read_text(encoding="utf-8"))
    outbound = json.loads(
        (ROOT / "agents/negotiator/data-collection.json").read_text(encoding="utf-8")
    )
    intake_fields = intake["fields"]
    outbound_fields = outbound["fields"]

    assert intake["agent_config_version"] == "2026-07-19.1"
    assert outbound["agent_config_version"] == "2026-07-19.1"
    assert len(intake_fields) == 24
    assert len(outbound_fields) == 14
    assert len(intake_fields) < 25
    assert len(outbound_fields) < 25
    assert [field["identifier"] for field in intake_fields] == [
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
    ]
    assert [field["identifier"] for field in outbound_fields] == [
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
    ]
    assert {field["type"] for field in intake_fields + outbound_fields} <= {
        "string",
        "boolean",
        "integer",
        "number",
    }
    assert len({field["identifier"] for field in intake_fields}) == len(intake_fields)
    assert len({field["identifier"] for field in outbound_fields}) == len(outbound_fields)

    intake_provider = elevenlabs_data_collection(intake)
    outbound_provider = elevenlabs_data_collection(outbound)
    assert list(intake_provider) == [field["identifier"] for field in intake_fields]
    assert list(outbound_provider) == [field["identifier"] for field in outbound_fields]
    assert all(
        set(provider_field) == {"type", "description"}
        for provider_field in (*intake_provider.values(), *outbound_provider.values())
    )


def test_elevenlabs_data_collection_transform_rejects_ambiguous_fields():
    with pytest.raises(ValueError, match="duplicate"):
        elevenlabs_data_collection(
            {
                "fields": [
                    {"identifier": "total", "type": "number", "description": "First."},
                    {"identifier": "total", "type": "number", "description": "Second."},
                ]
            }
        )
    with pytest.raises(ValueError, match="unsupported"):
        elevenlabs_data_collection(
            {"fields": [{"identifier": "items", "type": "array", "description": "Items."}]}
        )


def test_generated_fee_probes_cover_every_mandatory_category_once():
    config = yaml.safe_load((ROOT / "configs/moving.yaml").read_text(encoding="utf-8"))
    probes = (ROOT / "agents/negotiator/generated-fee-probes.md").read_text(encoding="utf-8")
    generated_categories = re.findall(r"^- `([a-z_]+)`: ", probes, flags=re.MULTILINE)
    assert generated_categories == config["mandatory_fee_questions"]
    assert len(generated_categories) == len(set(generated_categories))


def test_elevenlabs_dashboard_checklist_is_complete_and_secret_free():
    checklist = (ROOT / "agents/elevenlabs-dashboard-checklist.md").read_text(encoding="utf-8")
    lowered = checklist.lower()
    for phrase in (
        "veramove intake",
        "veramove outbound negotiator",
        "2026-07-19.1",
        "dynamic variables",
        "data collection",
        "success evaluation",
        "first message",
        "audio saving",
        "retention",
        "call limit",
        "conversation_initiation_client_data_webhook",
        "post_call_transcription",
        "retries",
        "audio webhook",
        "call_initiation_failure",
        "retry_enabled",
        "secret_id",
        "version_id",
        "branch_id",
        "assignment",
        "twilio recording",
    ):
        assert phrase in lowered
    assert "audio webhook: disabled" in lowered
    assert re.search(r"\+[1-9]\d{7,14}\b", checklist) is None
    for unsafe_key in ("xi-api-key", "sk-", "replace_me"):
        assert unsafe_key not in lowered
