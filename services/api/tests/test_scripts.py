"""Developer command construction tests."""

from pathlib import Path

from scripts.bootstrap import venv_python
from scripts.check import build_check_steps


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
