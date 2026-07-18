"""Acceptance checks for the public starter's required shape and boundaries."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_required_directories_and_files_exist():
    required = [
        "apps/web",
        "services/api/app/api",
        "services/api/app/contracts",
        "services/api/app/core",
        "services/api/app/orchestration",
        "services/api/app/repositories",
        "services/api/app/integrations/elevenlabs",
        "services/api/app/integrations/openai",
        "services/api/app/integrations/tavily",
        "services/api/tests",
        "agents/intake",
        "agents/negotiator",
        "packages/contracts/openapi.json",
        "configs/moving.yaml",
        "supabase/migrations/202607180001_initial_schema.sql",
        "data/demo",
        "evals",
        "scripts/bootstrap.py",
        "scripts/dev.py",
        "scripts/check.py",
        "scripts/export_openapi.py",
        "docs/architecture.md",
        "docs/api-contract.md",
        "docs/integration-boundaries.md",
        ".github/workflows/check.yml",
        ".github/pull_request_template.md",
        "README.md",
        "AGENTS.md",
        "LICENSE",
        ".gitignore",
        ".env.example",
        "CONTRIBUTING.md",
        "CODEOWNERS",
    ]
    assert not [path for path in required if not (ROOT / path).exists()]


def test_openapi_contains_every_required_core_contract():
    document = json.loads(
        (ROOT / "packages/contracts/openapi.json").read_text(encoding="utf-8")
    )
    schemas = document["components"]["schemas"]
    required = {
        "JobSpecV1",
        "OriginDestinationAccess",
        "InventoryItem",
        "MovingServices",
        "Vendor",
        "FeeLineItem",
        "TranscriptEvidence",
        "QuoteV1",
        "CallRecord",
        "CallOutcome",
        "RecommendationV1",
    }
    assert required <= schemas.keys()


def test_frontend_declares_all_required_routes_and_generated_contract_usage():
    routes = (ROOT / "apps/web/src/App.tsx").read_text(encoding="utf-8")
    for route in ("/intake", "/confirm/:jobId", "/calls/:jobId", "/report/:jobId"):
        assert f'path="{route}"' in routes
    client = (ROOT / "apps/web/src/api/client.ts").read_text(encoding="utf-8")
    assert 'from "./schema"' in client
    assert "components[\"schemas\"]" in client


def test_only_necessary_frontend_package_manifest_exists():
    manifests = [
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("package.json")
        if "node_modules" not in path.parts
    ]
    assert manifests == ["apps/web/package.json"]


def test_no_production_integration_sdk_or_optional_platform_dependency_is_declared():
    requirements = (ROOT / "services/api/requirements.txt").read_text(encoding="utf-8").lower()
    package = (ROOT / "apps/web/package.json").read_text(encoding="utf-8").lower()
    dependency_text = requirements + package
    for forbidden in (
        "elevenlabs",
        "twilio",
        "openai",
        "tavily",
        "supabase",
        "docker",
        "turbo",
        "nx",
    ):
        assert forbidden not in dependency_text


def test_sensitive_local_artifacts_are_absent_and_ignored():
    assert not (ROOT / ".env").exists()
    assert not list(ROOT.glob("*.sqlite*"))
    assert not (ROOT / "recordings").exists()
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", ".venv/", "node_modules/", "*.sqlite*", "recordings/"):
        assert pattern in ignore


def test_no_docker_or_unnecessary_monorepo_framework_files_exist():
    names = {
        path.name.lower()
        for path in ROOT.iterdir()
        if path.name not in {".git", ".venv"}
    }
    assert "dockerfile" not in names
    assert "docker-compose.yml" not in names
    assert "turbo.json" not in names
    assert "nx.json" not in names
