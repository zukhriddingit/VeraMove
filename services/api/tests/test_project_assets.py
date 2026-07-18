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
    assert "create index if not exists" in sql


def test_all_demo_json_is_explicitly_synthetic_or_covered_by_disclosure():
    readme = (ROOT / "data/demo/README.md").read_text(encoding="utf-8").lower()
    assert "every file" in readme and "synthetic" in readme
    policy_cards = json.loads(
        (ROOT / "data/demo/vendor_policy_cards.json").read_text(encoding="utf-8")
    )
    assert all(card["synthetic"] is True for card in policy_cards)


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
