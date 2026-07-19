"""Developer command construction tests."""

from pathlib import Path

from scripts.bootstrap import venv_python
from scripts.check import build_check_steps
from scripts.generate_agent_assets import GENERATED_ASSET_PATHS, generate_agent_assets


def test_bootstrap_uses_platform_venv_python(tmp_path):
    assert venv_python(tmp_path).name in {"python", "python.exe"}


def test_check_pipeline_has_required_order():
    assert [step.label for step in build_check_steps()] == [
        "Ruff",
        "pytest",
        "OpenAPI export",
        "API type generation",
        "frontend typecheck",
        "frontend tests",
        "frontend build",
    ]


def test_check_commands_are_root_relative():
    export = build_check_steps()[2]
    assert Path(export.command[1]) == Path("scripts/export_openapi.py")


def test_agent_asset_generator_is_deterministic_and_matches_committed_files(tmp_path):
    generated_root = tmp_path / "agents"
    generated_paths = generate_agent_assets(output_root=generated_root)

    assert [path.relative_to(generated_root) for path in generated_paths] == list(
        GENERATED_ASSET_PATHS
    )
    for relative_path in GENERATED_ASSET_PATHS:
        generated = (generated_root / relative_path).read_bytes()
        committed = (Path(__file__).resolve().parents[3] / "agents" / relative_path).read_bytes()
        assert generated == committed
