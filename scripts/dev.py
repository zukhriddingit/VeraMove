"""Run FastAPI and Vite together and stop both cleanly."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def venv_python() -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    directory = "Scripts" if os.name == "nt" else "bin"
    return ROOT / ".venv" / directory / executable


def npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def stop(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 5
    for process in processes:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main() -> int:
    python = venv_python()
    if not python.exists():
        print("Missing .venv. Run: python scripts/bootstrap.py", file=sys.stderr)
        return 1

    environment = os.environ.copy()
    environment.setdefault("APP_MODE", "mock")
    commands = [
        [
            str(python),
            "-m",
            "uvicorn",
            "services.api.app.main:app",
            "--reload",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        [npm_command(), "--prefix", "apps/web", "run", "dev"],
    ]
    processes = [subprocess.Popen(command, cwd=ROOT, env=environment) for command in commands]
    print("VeraMove API: http://127.0.0.1:8000/docs")
    print("VeraMove web: http://127.0.0.1:5173")
    print("Press Ctrl+C to stop both servers.")
    try:
        while True:
            for process in processes:
                if process.poll() is not None:
                    return process.returncode or 1
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nStopping VeraMove...")
        return 0
    finally:
        stop(processes)


if __name__ == "__main__":
    raise SystemExit(main())
