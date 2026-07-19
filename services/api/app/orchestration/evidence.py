"""Provider-neutral, transient transcript-to-evidence mapping."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from uuid import UUID, uuid5

from pydantic import HttpUrl

from services.api.app.contracts import DataClassification, TranscriptEvidence

MAX_EXCERPT_CHARACTERS = 1_000
MAX_EVIDENCE_DURATION_SECONDS = Decimal("30.00")
FINAL_TURN_DURATION_SECONDS = Decimal("15.00")
CENTISECOND = Decimal("0.01")


class TimestampedTranscriptTurn(Protocol):
    """Small structural boundary shared by provider transcript adapters."""

    message: str | None
    time_in_call_secs: Decimal


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    """One material claim and the transcript tokens required to support it."""

    claim: str
    phrases: tuple[str, ...]
    amount: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.claim.strip():
            raise ValueError("evidence claim must not be empty")
        if not self.phrases or any(not phrase.strip() for phrase in self.phrases):
            raise ValueError("evidence claim requires non-empty material phrases")


def build_transcript_evidence(
    *,
    call_id: UUID,
    recording_url: HttpUrl | str,
    transcript_turns: Sequence[TimestampedTranscriptTurn],
    claims: Sequence[EvidenceClaim],
    data_classification: DataClassification = DataClassification.ROLE_PLAY,
) -> list[TranscriptEvidence]:
    """Create bounded evidence for claims whose phrase and amount appear in one turn."""

    ordered_turns = sorted(
        enumerate(transcript_turns),
        key=lambda item: (Decimal(str(item[1].time_in_call_secs)), item[0]),
    )
    evidence: list[TranscriptEvidence] = []
    for claim in claims:
        match = _first_supporting_turn(ordered_turns, claim)
        if match is None:
            continue
        position, (_, turn) = match
        message = (turn.message or "").strip()[:MAX_EXCERPT_CHARACTERS]
        start = _centiseconds(turn.time_in_call_secs)
        end = _end_seconds(ordered_turns, position, start)
        evidence_id = uuid5(
            call_id,
            f"evidence:{claim.claim}:{start}:{message}",
        )
        evidence.append(
            TranscriptEvidence(
                evidence_id=evidence_id,
                call_id=call_id,
                excerpt=message,
                start_seconds=start,
                end_seconds=end,
                claim=claim.claim,
                recording_url=recording_url,
                data_classification=data_classification,
            )
        )
    return evidence


def _first_supporting_turn(
    ordered_turns: list[tuple[int, TimestampedTranscriptTurn]],
    claim: EvidenceClaim,
) -> tuple[int, tuple[int, TimestampedTranscriptTurn]] | None:
    for position, indexed_turn in enumerate(ordered_turns):
        message = indexed_turn[1].message
        if not message:
            continue
        searchable = _searchable(message)
        if not all(_searchable(phrase) in searchable for phrase in claim.phrases):
            continue
        if claim.amount is not None and not _contains_amount(searchable, claim.amount):
            continue
        return position, indexed_turn
    return None


def _searchable(value: str) -> str:
    without_separators = value.lower().replace(",", "").replace("$", "")
    return " ".join(re.sub(r"[^a-z0-9.]+", " ", without_separators).split())


def _contains_amount(searchable: str, amount: Decimal) -> bool:
    exact = format(amount, "f")
    compact = exact.rstrip("0").rstrip(".")
    patterns = {re.escape(exact), re.escape(compact)}
    return any(
        re.search(rf"(?<!\d){pattern}(?!\d)", searchable) is not None for pattern in patterns
    )


def _centiseconds(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(CENTISECOND, rounding=ROUND_HALF_UP)


def _end_seconds(
    ordered_turns: list[tuple[int, TimestampedTranscriptTurn]],
    position: int,
    start: Decimal,
) -> Decimal:
    maximum = start + MAX_EVIDENCE_DURATION_SECONDS
    if position + 1 >= len(ordered_turns):
        return start + FINAL_TURN_DURATION_SECONDS
    next_start = _centiseconds(ordered_turns[position + 1][1].time_in_call_secs)
    return max(start, min(next_start, maximum))
