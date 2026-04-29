import asyncio
import uuid

import pytest


async def _poll_status(client, job_id, target, timeout=10):
    for _ in range(timeout * 10):
        resp = await client.get(f"/api/v1/jobs/{job_id}")
        if resp.json()["status"] == target:
            return resp.json()
        await asyncio.sleep(0.1)
    raise TimeoutError(f"job {job_id} did not reach '{target}' within {timeout}s")


@pytest.mark.integration
async def test_full_pipeline_completes_with_all_stages(client, redis_client):
    resp = await client.post(
        "/api/v1/jobs",
        json={
            "document_name": "report.pdf",
            "document_type": "pdf",
            "document_content": "hello world test content",
            "pipeline_config": ["extraction", "analysis", "enrichment"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    job_id = data["id"]

    job = await _poll_status(client, job_id, "completed")
    assert job["partial_results"] is not None
    assert set(job["partial_results"].keys()) == {"extraction", "analysis", "enrichment"}
    assert job["error_message"] is None

    entries = await redis_client.xrange("jobs:events", "-", "+")
    job_events = [e[1] for e in entries if e[1].get("job_id") == job_id]
    event_types = {e["event_type"] for e in job_events}
    assert {"job.created", "job.stage_started", "job.stage_completed", "job.completed"}.issubset(
        event_types
    )
    started = [e for e in job_events if e["event_type"] == "job.stage_started"]
    completed_stages = [e for e in job_events if e["event_type"] == "job.stage_completed"]
    assert len(started) == 3
    assert len(completed_stages) == 3


@pytest.mark.integration
async def test_partial_pipeline_extraction_only(client):
    resp = await client.post(
        "/api/v1/jobs",
        json={
            "document_name": "doc.txt",
            "document_type": "txt",
            "document_content": "just some text",
            "pipeline_config": ["extraction"],
        },
    )
    assert resp.status_code == 201
    job_id = resp.json()["id"]

    job = await _poll_status(client, job_id, "completed")
    assert set(job["partial_results"].keys()) == {"extraction"}


@pytest.mark.integration
async def test_list_jobs_filter_by_status(client):
    resp = await client.post(
        "/api/v1/jobs",
        json={
            "document_name": "listed.pdf",
            "document_type": "pdf",
            "document_content": "content",
            "pipeline_config": ["extraction"],
        },
    )
    job_id = resp.json()["id"]
    await _poll_status(client, job_id, "completed")

    resp = await client.get("/api/v1/jobs?status=completed")
    assert resp.status_code == 200
    ids = [j["id"] for j in resp.json()]
    assert job_id in ids

    resp = await client.get("/api/v1/jobs?status=pending")
    assert resp.status_code == 200
    pending_ids = [j["id"] for j in resp.json()]
    assert job_id not in pending_ids


@pytest.mark.integration
async def test_cancel_completed_job_returns_409(client):
    resp = await client.post(
        "/api/v1/jobs",
        json={
            "document_name": "done.pdf",
            "document_type": "pdf",
            "document_content": "content",
            "pipeline_config": ["extraction"],
        },
    )
    job_id = resp.json()["id"]
    await _poll_status(client, job_id, "completed")

    resp = await client.delete(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 409


@pytest.mark.integration
async def test_get_nonexistent_job_returns_404(client):
    resp = await client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.integration
async def test_cancel_nonexistent_job_returns_404(client):
    resp = await client.delete(f"/api/v1/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.integration
async def test_get_job_returns_partial_results_before_completion(client):
    resp = await client.post(
        "/api/v1/jobs",
        json={
            "document_name": "check.pdf",
            "document_type": "pdf",
            "document_content": "content",
            "pipeline_config": ["extraction", "analysis"],
        },
    )
    assert resp.status_code == 201
    job_id = resp.json()["id"]

    job = await _poll_status(client, job_id, "completed")
    assert "extraction" in job["partial_results"]
    assert "analysis" in job["partial_results"]
