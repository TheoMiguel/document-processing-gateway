import enum


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class InvalidTransitionError(Exception):
    pass


_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.pending: {JobStatus.processing, JobStatus.cancelled},
    JobStatus.processing: {JobStatus.completed, JobStatus.failed, JobStatus.cancelled},
    JobStatus.completed: set(),
    JobStatus.failed: set(),
    JobStatus.cancelled: set(),
}


def transition(current: JobStatus, target: JobStatus) -> JobStatus:
    if target not in _TRANSITIONS[current]:
        raise InvalidTransitionError(f"Cannot transition from {current} to {target}")
    return target
