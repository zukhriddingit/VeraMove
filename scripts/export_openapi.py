"""Export FastAPI's canonical OpenAPI contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.api.app.main import app  # noqa: E402

DEFAULT_TARGET = ROOT / "packages" / "contracts" / "openapi.json"


def export_openapi(target: Path = DEFAULT_TARGET) -> Path:
    """Write deterministic OpenAPI JSON and return its path."""

    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    target.write_text(payload, encoding="utf-8")
    return target


def main() -> int:
    target = export_openapi()
    print(f"Exported OpenAPI to {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
