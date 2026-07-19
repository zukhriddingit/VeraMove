"""Typed loader for clearly synthetic demo fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.api.app.contracts import (
    JobSpecV1,
    QuoteV1,
    RecommendationV1,
    TranscriptEvidence,
    Vendor,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DEMO_ROOT = REPO_ROOT / "data" / "demo"


class DemoFixtures:
    def __init__(self, root: Path = DEMO_ROOT) -> None:
        self._root = root

    def load_job(self) -> JobSpecV1:
        return JobSpecV1.model_validate(self._read("job.json"))

    def load_vendors(self) -> list[Vendor]:
        return [Vendor.model_validate(item) for item in self._read("vendors.json")]

    def load_live_role_play_vendors(self) -> list[Vendor]:
        """Return the fictional vendor identities reserved for supervised calls."""

        return [
            Vendor.model_validate(item)
            for item in self._read("live_role_play_vendors.json")
        ]

    def load_initial_quotes(self) -> list[QuoteV1]:
        return [QuoteV1.model_validate(item) for item in self._read("initial_quotes.json")]

    def load_negotiated_quote(self) -> QuoteV1:
        return QuoteV1.model_validate(self._read("negotiated_quote.json"))

    def load_evidence(self) -> list[TranscriptEvidence]:
        return [
            TranscriptEvidence.model_validate(item)
            for item in self._read("transcript_evidence.json")
        ]

    def load_recommendation(self) -> RecommendationV1:
        return RecommendationV1.model_validate(self._read("recommendation.json"))

    def _read(self, filename: str) -> Any:
        return json.loads((self._root / filename).read_text(encoding="utf-8"))
