"""Documentation and ownership completeness tests."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
README = (ROOT / "README.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
CONTRIBUTING = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
INTAKE_AGENT = (ROOT / "agents/intake/README.md").read_text(encoding="utf-8")
NEGOTIATOR_AGENT = (ROOT / "agents/negotiator/README.md").read_text(encoding="utf-8")


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


def test_agents_declares_final_role_ownership_and_boundaries():
    for owner in (
        "Toheeb (@Olacode01)",
        "Zukhriuddin (@zukhriddingit)",
        "Northeastern teammate",
        "Arsalan (@ars2711)",
    ):
        assert owner in AGENTS
    assert "Do not rewrite another member's subsystem" in AGENTS
    assert "No-secrets rule" in AGENTS
    assert "No-real-PII rule" in AGENTS
    assert "Contract-change process" in AGENTS
    assert "python scripts/check.py" in AGENTS


def test_contributor_and_agent_docs_use_role_ownership():
    assert "role-scoped branch" in CONTRIBUTING
    assert "Owner: Toheeb (@Olacode01)" in INTAKE_AGENT
    assert "Owner: Toheeb (@Olacode01)" in NEGOTIATOR_AGENT


def test_ci_has_no_deployment_or_secret_context():
    workflow = (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8").lower()
    assert "python scripts/check.py" in workflow
    assert "pull_request" in workflow
    assert "branches: [main]" in workflow
    assert "deploy" not in workflow
    assert "secrets." not in workflow
