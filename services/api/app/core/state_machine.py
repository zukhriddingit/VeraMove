"""Explicit legal transitions for the VeraMove job lifecycle."""

from services.api.app.contracts import JobState
from services.api.app.core.errors import InvalidStateTransition

TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.DRAFT: frozenset({JobState.INTAKE_COMPLETE}),
    JobState.INTAKE_COMPLETE: frozenset({JobState.CONFIRMED, JobState.FAILED}),
    JobState.CONFIRMED: frozenset({JobState.CALLING, JobState.FAILED}),
    JobState.CALLING: frozenset({JobState.QUOTES_READY, JobState.FAILED}),
    JobState.QUOTES_READY: frozenset({JobState.NEGOTIATING, JobState.FAILED}),
    JobState.NEGOTIATING: frozenset({JobState.COMPLETED, JobState.FAILED}),
    JobState.COMPLETED: frozenset(),
    JobState.FAILED: frozenset(),
}


def validate_transition(current: JobState, target: JobState) -> None:
    """Raise a clear domain error when a transition is not legal."""

    if target not in TRANSITIONS[current]:
        message = f"Illegal job state transition: {current.value} -> {target.value}"
        raise InvalidStateTransition(message)
