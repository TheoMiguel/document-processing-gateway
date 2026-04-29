import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tenacity import stop_after_attempt, wait_none

from app.core.orchestrator import PipelineOrchestrator
from app.core.state_machine import JobStatus


class FakeJob:
    def __init__(self, pipeline_config=None):
        self.id = uuid.uuid4()
        self.pipeline_config = pipeline_config or ["extraction", "analysis", "enrichment"]
        self.document_content = "test content"
        self.document_type = "pdf"
        self.status = JobStatus.pending
        self.partial_results = None
        self.error_message = None
        self.updated_at = None


def _fast_retry(reraise=True):
    return {"stop": stop_after_attempt(1), "wait": wait_none(), "reraise": reraise}


def _make_session_patch(fake_job):
    mock_db = MagicMock()
    mock_db.get = AsyncMock(return_value=fake_job)
    mock_db.commit = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_db

    mock_factory = MagicMock(return_value=mock_cm)
    return mock_factory, mock_db


@pytest.fixture
def mock_publisher():
    return AsyncMock()


def _published_event_types(mock_publisher):
    return [c[0][0] for c in mock_publisher.publish.call_args_list]


async def test_full_pipeline_all_three_stages(mock_publisher):
    fake_job = FakeJob(["extraction", "analysis", "enrichment"])
    mock_factory, _ = _make_session_patch(fake_job)

    extraction = AsyncMock()
    extraction.extract.return_value = {"text": "extracted"}
    analysis = AsyncMock()
    analysis.analyze.return_value = {"sentiment": "neutral"}
    enrichment = AsyncMock()
    enrichment.enrich.return_value = {"entities": []}

    orchestrator = PipelineOrchestrator(extraction, analysis, enrichment, mock_publisher)

    with patch("app.core.orchestrator.AsyncSessionLocal", mock_factory):
        with patch("app.core.orchestrator._retry_kwargs", return_value=_fast_retry()):
            await orchestrator.run(fake_job.id)

    assert fake_job.status == JobStatus.completed
    extraction.extract.assert_called_once_with("test content", "pdf")
    analysis.analyze.assert_called_once()
    enrichment.enrich.assert_called_once()

    events = _published_event_types(mock_publisher)
    assert events.count("job.stage_started") == 3
    assert events.count("job.stage_completed") == 3
    assert "job.completed" in events


async def test_partial_pipeline_extraction_only(mock_publisher):
    fake_job = FakeJob(["extraction"])
    mock_factory, _ = _make_session_patch(fake_job)

    extraction = AsyncMock()
    extraction.extract.return_value = {"text": "extracted"}
    analysis = AsyncMock()
    enrichment = AsyncMock()

    orchestrator = PipelineOrchestrator(extraction, analysis, enrichment, mock_publisher)

    with patch("app.core.orchestrator.AsyncSessionLocal", mock_factory):
        with patch("app.core.orchestrator._retry_kwargs", return_value=_fast_retry()):
            await orchestrator.run(fake_job.id)

    assert fake_job.status == JobStatus.completed
    extraction.extract.assert_called_once()
    analysis.analyze.assert_not_called()
    enrichment.enrich.assert_not_called()

    events = _published_event_types(mock_publisher)
    assert events.count("job.stage_started") == 1
    assert "job.completed" in events


async def test_stage_ordering_enforced_regardless_of_config(mock_publisher):
    # pipeline_config has wrong order — orchestrator must still run extraction before analysis
    fake_job = FakeJob(["analysis", "extraction"])
    mock_factory, _ = _make_session_patch(fake_job)

    call_order = []

    extraction = AsyncMock()
    extraction.extract = AsyncMock(
        side_effect=lambda *a: call_order.append("extraction") or {"text": "x"}
    )
    analysis = AsyncMock()
    analysis.analyze = AsyncMock(
        side_effect=lambda *a: call_order.append("analysis") or {"sentiment": "n"}
    )
    enrichment = AsyncMock()

    orchestrator = PipelineOrchestrator(extraction, analysis, enrichment, mock_publisher)

    with patch("app.core.orchestrator.AsyncSessionLocal", mock_factory):
        with patch("app.core.orchestrator._retry_kwargs", return_value=_fast_retry()):
            await orchestrator.run(fake_job.id)

    assert call_order == ["extraction", "analysis"]


async def test_partial_results_accumulated_across_stages(mock_publisher):
    fake_job = FakeJob(["extraction", "analysis", "enrichment"])
    mock_factory, _ = _make_session_patch(fake_job)

    extraction = AsyncMock()
    extraction.extract.return_value = {"text": "extracted"}
    analysis = AsyncMock()
    analysis.analyze.return_value = {"sentiment": "neutral"}
    enrichment = AsyncMock()
    enrichment.enrich.return_value = {"entities": []}

    orchestrator = PipelineOrchestrator(extraction, analysis, enrichment, mock_publisher)

    with patch("app.core.orchestrator.AsyncSessionLocal", mock_factory):
        with patch("app.core.orchestrator._retry_kwargs", return_value=_fast_retry()):
            await orchestrator.run(fake_job.id)

    assert fake_job.partial_results == {
        "extraction": {"text": "extracted"},
        "analysis": {"sentiment": "neutral"},
        "enrichment": {"entities": []},
    }


async def test_provider_failure_marks_job_failed(mock_publisher):
    # With reraise=True (production default), original exception hits `except Exception`
    fake_job = FakeJob(["extraction"])
    mock_factory, _ = _make_session_patch(fake_job)

    extraction = AsyncMock()
    extraction.extract.side_effect = RuntimeError("provider down")

    orchestrator = PipelineOrchestrator(extraction, AsyncMock(), AsyncMock(), mock_publisher)

    with patch("app.core.orchestrator.AsyncSessionLocal", mock_factory):
        with patch("app.core.orchestrator._retry_kwargs", return_value=_fast_retry(reraise=True)):
            await orchestrator.run(fake_job.id)

    assert fake_job.status == JobStatus.failed
    assert "provider down" in fake_job.error_message
    assert "job.failed" in _published_event_types(mock_publisher)


async def test_provider_failure_sends_to_dlq_on_retry_error(mock_publisher):
    # With reraise=False, RetryError is raised and handled by the except RetryError block → DLQ
    fake_job = FakeJob(["extraction"])
    mock_factory, _ = _make_session_patch(fake_job)

    extraction = AsyncMock()
    extraction.extract.side_effect = RuntimeError("transient error")

    orchestrator = PipelineOrchestrator(extraction, AsyncMock(), AsyncMock(), mock_publisher)

    with patch("app.core.orchestrator.AsyncSessionLocal", mock_factory):
        with patch("app.core.orchestrator._retry_kwargs", return_value=_fast_retry(reraise=False)):
            await orchestrator.run(fake_job.id)

    assert fake_job.status == JobStatus.failed
    assert "job.failed" in _published_event_types(mock_publisher)
    mock_publisher.publish_dlq.assert_called_once()


async def test_unknown_stage_fails_immediately(mock_publisher):
    fake_job = FakeJob(["unknown_stage"])
    mock_factory, _ = _make_session_patch(fake_job)

    orchestrator = PipelineOrchestrator(AsyncMock(), AsyncMock(), AsyncMock(), mock_publisher)

    with patch("app.core.orchestrator.AsyncSessionLocal", mock_factory):
        await orchestrator.run(fake_job.id)

    assert fake_job.status == JobStatus.failed
    assert "Unknown stages" in fake_job.error_message
    assert "job.failed" in _published_event_types(mock_publisher)


async def test_missing_job_id_is_noop(mock_publisher):
    mock_factory, mock_db = _make_session_patch(None)
    mock_db.get.return_value = None

    orchestrator = PipelineOrchestrator(AsyncMock(), AsyncMock(), AsyncMock(), mock_publisher)

    with patch("app.core.orchestrator.AsyncSessionLocal", mock_factory):
        await orchestrator.run(uuid.uuid4())

    mock_publisher.publish.assert_not_called()
