"""Create a local environment and install all starter dependencies."""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def venv_python(root: Path = ROOT) -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    directory = "Scripts" if os.name == "nt" else "bin"
    return root / ".venv" / directory / executable


def npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def run(label: str, command: list[str]) -> None:
    print(f"\n==> {label}")
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    environment = ROOT / ".venv"
    if not environment.exists():
        print("==> Creating .venv")
        venv.EnvBuilder(with_pip=True).create(environment)
    else:
        print("==> Reusing .venv")

    python = str(venv_python())
    npm = npm_command()
    run(
        "Installing backend dependencies",
        [python, "-m", "pip", "install", "-r", "services/api/requirements-dev.txt"],
    )
    run("Installing frontend dependencies", [npm, "install", "--prefix", "apps/web"])
    run("Exporting canonical OpenAPI", [python, "scripts/export_openapi.py"])
    run("Generating frontend API types", [npm, "--prefix", "apps/web", "run", "generate:api"])

    print("\nBootstrap complete.")
    print("Next: python scripts/dev.py")
    print("Check: python scripts/check.py")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Bootstrap failed during: {' '.join(exc.cmd)}", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
