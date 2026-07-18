"""Run every repository quality gate in a deterministic order."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class CheckStep:
    label: str
    command: tuple[str, ...]


def venv_python(root: Path = ROOT) -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    directory = "Scripts" if os.name == "nt" else "bin"
    return root / ".venv" / directory / executable


def npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def build_check_steps() -> tuple[CheckStep, ...]:
    python_path = venv_python()
    python = str(python_path if python_path.exists() else Path(sys.executable))
    npm = npm_command()
    return (
        CheckStep("Ruff", (python, "-m", "ruff", "check", ".")),
        CheckStep("pytest", (python, "-m", "pytest", "-q")),
        CheckStep("OpenAPI export", (python, "scripts/export_openapi.py")),
        CheckStep(
            "API type generation",
            (npm, "--prefix", "apps/web", "run", "generate:api"),
        ),
        CheckStep("frontend typecheck", (npm, "--prefix", "apps/web", "run", "typecheck")),
        CheckStep("frontend tests", (npm, "--prefix", "apps/web", "test")),
        CheckStep("frontend build", (npm, "--prefix", "apps/web", "run", "build")),
    )


def main() -> int:
    for step in build_check_steps():
        print(f"\n==> {step.label}")
        result = subprocess.run(step.command, cwd=ROOT, check=False)
        if result.returncode:
            print(f"{step.label} failed with exit code {result.returncode}", file=sys.stderr)
            return result.returncode
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
