import pytest

from app.core.state_machine import InvalidTransitionError, JobStatus, transition


def test_pending_to_processing():
    assert transition(JobStatus.pending, JobStatus.processing) == JobStatus.processing


def test_pending_to_cancelled():
    assert transition(JobStatus.pending, JobStatus.cancelled) == JobStatus.cancelled


def test_processing_to_completed():
    assert transition(JobStatus.processing, JobStatus.completed) == JobStatus.completed


def test_processing_to_failed():
    assert transition(JobStatus.processing, JobStatus.failed) == JobStatus.failed


def test_processing_to_cancelled():
    assert transition(JobStatus.processing, JobStatus.cancelled) == JobStatus.cancelled


def test_pending_to_failed():
    assert transition(JobStatus.pending, JobStatus.failed) == JobStatus.failed


@pytest.mark.parametrize(
    "current, target",
    [
        (JobStatus.pending, JobStatus.completed),
        (JobStatus.pending, JobStatus.pending),
        (JobStatus.processing, JobStatus.pending),
        (JobStatus.processing, JobStatus.processing),
    ],
)
def test_invalid_transitions(current, target):
    with pytest.raises(InvalidTransitionError):
        transition(current, target)


@pytest.mark.parametrize("terminal", [JobStatus.completed, JobStatus.failed, JobStatus.cancelled])
def test_terminal_states_reject_all(terminal):
    for target in JobStatus:
        with pytest.raises(InvalidTransitionError):
            transition(terminal, target)
