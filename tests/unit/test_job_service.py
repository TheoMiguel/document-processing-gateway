import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.state_machine import InvalidTransitionError, JobStatus
from app.models.job import Job
from app.services.job_service import JobNotFoundError, JobService


def make_fake_job(**kwargs):
    job = MagicMock(spec=Job)
    job.id = kwargs.get("id", uuid.uuid4())
    job.document_name = kwargs.get("document_name", "doc.pdf")
    job.document_type = kwargs.get("document_type", "pdf")
    job.document_content = kwargs.get("document_content", "hello world")
    job.pipeline_config = kwargs.get("pipeline_config", ["extraction"])
    job.status = kwargs.get("status", JobStatus.pending)
    return job


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_publisher():
    return AsyncMock()


@pytest.fixture
def service(mock_db, mock_publisher):
    return JobService(mock_db, mock_publisher)


async def test_create_adds_commits_and_publishes(service, mock_db, mock_publisher):
    await service.create("doc.pdf", "pdf", "hello", ["extraction"])

    mock_db.add.assert_called_once()
    added = mock_db.add.call_args[0][0]
    assert isinstance(added, Job)
    assert added.document_name == "doc.pdf"
    assert added.document_type == "pdf"
    assert added.status == JobStatus.pending

    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once()

    mock_publisher.publish.assert_called_once()
    event_type, _job_id, payload = mock_publisher.publish.call_args[0]
    assert event_type == "job.created"
    assert payload["document_name"] == "doc.pdf"
    assert payload["pipeline_config"] == ["extraction"]


async def test_get_found(service, mock_db):
    fake_job = make_fake_job()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_job
    mock_db.execute.return_value = mock_result

    result = await service.get(fake_job.id)
    assert result is fake_job


async def test_get_not_found(service, mock_db):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(JobNotFoundError):
        await service.get(uuid.uuid4())


async def test_list_no_filter_returns_all(service, mock_db):
    jobs = [make_fake_job(), make_fake_job()]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = jobs
    mock_db.execute.return_value = mock_result

    result = await service.list()
    assert result == jobs
    mock_db.execute.assert_called_once()


async def test_list_with_status_filter(service, mock_db):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    await service.list(status=JobStatus.completed)
    mock_db.execute.assert_called_once()


async def test_cancel_pending_job_transitions_and_publishes(service, mock_db, mock_publisher):
    fake_job = make_fake_job(status=JobStatus.pending)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_job
    mock_db.execute.return_value = mock_result

    result = await service.cancel(fake_job.id)

    assert result.status == JobStatus.cancelled
    mock_db.commit.assert_called_once()
    mock_publisher.publish.assert_called_once()
    event_type = mock_publisher.publish.call_args[0][0]
    assert event_type == "job.cancelled"


async def test_cancel_completed_job_raises_invalid_transition(service, mock_db, mock_publisher):
    fake_job = make_fake_job(status=JobStatus.completed)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_job
    mock_db.execute.return_value = mock_result

    with pytest.raises(InvalidTransitionError):
        await service.cancel(fake_job.id)

    mock_publisher.publish.assert_not_called()


async def test_cancel_failed_job_raises_invalid_transition(service, mock_db, mock_publisher):
    fake_job = make_fake_job(status=JobStatus.failed)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_job
    mock_db.execute.return_value = mock_result

    with pytest.raises(InvalidTransitionError):
        await service.cancel(fake_job.id)


async def test_cancel_not_found(service, mock_db):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(JobNotFoundError):
        await service.cancel(uuid.uuid4())
