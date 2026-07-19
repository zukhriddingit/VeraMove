"""Grounded recommendation narration that cannot change deterministic ranking."""

from __future__ import annotations

import os

from services.api.app.contracts import (
    IntelligenceFinding,
    JobSpecV1,
    RecommendationRanking,
)
from services.api.app.integrations.openai.base import GroundedNarrativeClient


class OpenAIRecommendationNarrator:
    def __init__(
        self,
        client: GroundedNarrativeClient,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._model = model or os.getenv("OPENAI_RECOMMENDATION_MODEL", "gpt-4.1-mini")

    def explain(
        self,
        job_spec: JobSpecV1,
        rankings: list[RecommendationRanking],
        findings: list[IntelligenceFinding],
    ) -> str:
        summary = self._client.explain(
            model=self._model,
            job_spec=job_spec,
            rankings=rankings,
            findings=findings,
        ).strip()
        if not summary:
            raise ValueError("recommendation narrator returned an empty explanation")
        if len(summary) > 1000:
            raise ValueError("recommendation narrator exceeded the contract limit")
        return summary
