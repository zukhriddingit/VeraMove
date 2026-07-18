"""Job lifecycle transition tests."""

import pytest

from services.api.app.contracts import JobState
from services.api.app.core.errors import InvalidStateTransition
from services.api.app.core.state_machine import validate_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (JobState.DRAFT, JobState.INTAKE_COMPLETE),
        (JobState.INTAKE_COMPLETE, JobState.CONFIRMED),
        (JobState.CONFIRMED, JobState.CALLING),
        (JobState.CALLING, JobState.QUOTES_READY),
        (JobState.QUOTES_READY, JobState.NEGOTIATING),
        (JobState.NEGOTIATING, JobState.COMPLETED),
    ],
)
def test_happy_path_transitions(current, target):
    validate_transition(current, target)


@pytest.mark.parametrize(
    "current",
    [
        JobState.INTAKE_COMPLETE,
        JobState.CONFIRMED,
        JobState.CALLING,
        JobState.QUOTES_READY,
        JobState.NEGOTIATING,
    ],
)
def test_active_state_can_fail(current):
    validate_transition(current, JobState.FAILED)


def test_illegal_transition_has_clear_message():
    with pytest.raises(InvalidStateTransition, match="confirmed -> completed"):
        validate_transition(JobState.CONFIRMED, JobState.COMPLETED)


@pytest.mark.parametrize("terminal", [JobState.COMPLETED, JobState.FAILED])
def test_terminal_states_are_terminal(terminal):
    with pytest.raises(InvalidStateTransition):
        validate_transition(terminal, JobState.CALLING)
