"""Documentation and ownership completeness tests."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
README = (ROOT / "README.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
CONTRIBUTING = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
INTAKE_AGENT = (ROOT / "agents/intake/README.md").read_text(encoding="utf-8")
NEGOTIATOR_AGENT = (ROOT / "agents/negotiator/README.md").read_text(encoding="utf-8")
BACKEND_VOICE_RUNBOOK = (ROOT / "docs/backend-voice-runbook.md").read_text(
    encoding="utf-8"
)
BACKEND_VOICE_PR_SUMMARY = (ROOT / "docs/backend-voice-pr-summary.md").read_text(
    encoding="utf-8"
)


@pytest.mark.parametrize(
    "heading",
    [
        "Product summary",
        "Architecture",
        "Repository structure",
        "Prerequisites",
        "Five-minute local setup",
        "Environment variables",
        "Mock mode",
        "Commands",
        "API routes",
        "Team branch conventions",
        "Known limitations",
        "Synthetic data",
        "Future VeraAI integration",
    ],
)
def test_readme_has_required_sections(heading):
    assert f"## {heading}" in README


def test_agents_declares_all_member_ownership_and_boundaries():
    for name in ["Prathmesh", "Zukhriuddin", "Toheeb", "Arsalan"]:
        assert name in AGENTS
    assert "Do not rewrite another member's subsystem" in AGENTS
    assert "No-secrets rule" in AGENTS
    assert "No-real-PII rule" in AGENTS
    assert "Contract-change process" in AGENTS
    assert "python scripts/check.py" in AGENTS


def test_contributor_and_agent_docs_use_role_ownership():
    assert "role-scoped branch" in CONTRIBUTING
    assert "Owner: Prathmesh" in INTAKE_AGENT
    assert "Owner: Prathmesh" in NEGOTIATOR_AGENT


def test_ci_has_no_deployment_or_secret_context():
    workflow = (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8").lower()
    assert "python scripts/check.py" in workflow
    assert "pull_request" in workflow
    assert "branches: [main]" in workflow
    assert "deploy" not in workflow
    assert "secrets." not in workflow


def test_backend_voice_runbook_documents_reproducible_mock_smoke_order():
    for command in (
        "python scripts/bootstrap.py",
        "python scripts/check.py",
        "APP_MODE=mock python scripts/dev.py",
    ):
        assert command in BACKEND_VOICE_RUNBOOK

    route_order = (
        "/api/intake/document",
        "/confirm",
        "/calls",
        "/negotiate",
        "/report",
        "/events",
    )
    positions = [BACKEND_VOICE_RUNBOOK.index(route) for route in route_order]
    assert positions == sorted(positions)
    assert "repeated confirmation and call-batch requests are safe" in (
        BACKEND_VOICE_RUNBOOK.lower()
    )
    assert "synthetic" in BACKEND_VOICE_RUNBOOK.lower()


def test_backend_voice_runbook_documents_fail_closed_live_and_release_gates():
    for safety_fact in (
        "APP_MODE=live",
        "LIVE_CALLS_ENABLED=true",
        "LIVE_TEST_TO_NUMBERS",
        "Do not run the live smoke test from CI",
        "--confirm-supervised-one-call",
        "scripts/live_voice_preflight.py --check-only",
        "scripts/live_voice_smoke.py",
        "three-call run",
        "not ElevenLabs Batch Calling",
        "Audio Saving",
        "nonzero retention",
        "post-call transcription retries",
        "/api/webhooks/elevenlabs/pre-call",
        "/api/webhooks/elevenlabs",
        "three consenting",
        "202607190003_live_voice_materialization.sql",
        "202607190004_atomic_voice_intake.sql",
        "repair",
        "APP_MODE=mock",
        "unset",
        "No release tag before code freeze",
    ):
        assert safety_fact in BACKEND_VOICE_RUNBOOK


def test_backend_voice_pr_summary_records_contract_and_operational_limits():
    for heading in (
        "Summary",
        "Routes",
        "Safety controls",
        "Test evidence",
        "Contract impact",
        "Known limitations",
    ):
        assert f"## {heading}" in BACKEND_VOICE_PR_SUMMARY
    normalized_summary = " ".join(BACKEND_VOICE_PR_SUMMARY.lower().split())
    for fact in (
        "supabase",
        "exactly three",
        "two agent roles",
        "canonical report",
        "optional for non-quote",
        "raw transcript",
        "no release tag",
    ):
        assert fact in normalized_summary


def test_live_voice_docs_remove_obsolete_one_call_limitations():
    combined = "\n".join(
        (
            README,
            (ROOT / "docs/architecture.md").read_text(encoding="utf-8"),
            (ROOT / "docs/integration-boundaries.md").read_text(encoding="utf-8"),
            BACKEND_VOICE_RUNBOOK,
            BACKEND_VOICE_PR_SUMMARY,
        )
    ).lower()
    for obsolete in (
        "at most one opted-in test call",
        "does not produce a live report",
        "does not materialize a canonical quote",
        "one externally supplied test destination",
        "one-call voice adapter",
    ):
        assert obsolete not in combined


def test_readme_and_architecture_document_two_roles_and_exact_three_flow():
    combined = "\n".join(
        (
            README,
            (ROOT / "docs/architecture.md").read_text(encoding="utf-8"),
            (ROOT / "docs/integration-boundaries.md").read_text(encoding="utf-8"),
        )
    )
    for fact in (
        "VeraMove Intake",
        "VeraMove Outbound Negotiator",
        "exactly three",
        "same locked JobSpec",
        "call_mode=quote",
        "call_mode=negotiation",
    ):
        assert fact in combined
