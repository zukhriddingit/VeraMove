"""Structural checks for configuration, fixtures, and migration assets."""

import json
from pathlib import Path

import yaml

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


def test_voice_agent_assets_are_safe_and_machine_readable():
    intake_prompt = (ROOT / "agents/intake/prompt.md").read_text(encoding="utf-8")
    negotiator_prompt = (ROOT / "agents/negotiator/prompt.md").read_text(encoding="utf-8")
    intake_config = yaml.safe_load(
        (ROOT / "agents/intake/agent.yaml").read_text(encoding="utf-8"),
    )
    negotiator_config = yaml.safe_load(
        (ROOT / "agents/negotiator/agent.yaml").read_text(encoding="utf-8"),
    )
    tools = yaml.safe_load((ROOT / "agents/tools.yaml").read_text(encoding="utf-8"))

    assert "Ask only for fields configured in configs/moving.yaml" in intake_prompt
    assert "never infer inventory, access, price, or insurance facts" in intake_prompt
    assert "Never confirm a job or place a vendor call yourself" in intake_prompt
    assert "Use get_verified_competing_quote before mentioning a competitor" in (
        negotiator_prompt
    )
    assert "Never invent a price, fee, concession, recording" in negotiator_prompt
    assert "exactly one supported CallOutcome type" in negotiator_prompt

    assert intake_config["version"] == 1
    assert intake_config["agent"] == {
        "name": "veramove-intake",
        "prompt_file": "prompt.md",
        "tools_file": "../tools.yaml",
        "tool_names": [],
        "structured_output": "JobSpecV1",
    }
    assert negotiator_config["agent"]["name"] == "veramove-negotiator"
    assert negotiator_config["agent"]["structured_output"] == "CallOutcome"
    assert negotiator_config["agent"]["tool_names"] == [
        "save_quote",
        "save_call_outcome",
        "get_verified_competing_quote",
        "request_callback",
    ]

    tool_names = [tool["name"] for tool in tools["tools"]]
    assert tool_names == negotiator_config["agent"]["tool_names"]
    assert all("required" in tool and "properties" in tool for tool in tools["tools"])
    serialized = "\n".join(
        (intake_prompt, negotiator_prompt, yaml.safe_dump(intake_config), yaml.safe_dump(tools)),
    ).lower()
    for unsafe_key in ("xi-api-key", "sk-", "phone_number", "@example.com"):
        assert unsafe_key not in serialized
