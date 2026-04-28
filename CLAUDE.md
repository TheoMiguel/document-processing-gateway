# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Document Processing Gateway — a FastAPI microservice that orchestrates document processing through a pipeline of external providers and publishes events to Redis Streams.

## Commands

```bash
# Install / sync deps (uses uv)
uv sync --extra dev

# Start all services
docker compose up --build

# Start only infra (postgres + redis), run API locally
docker compose up postgres redis -d
.venv/bin/uvicorn app.main:app --reload

# Run all tests
.venv/bin/pytest

# Run a single test file
.venv/bin/pytest tests/unit/test_state_machine.py

# Run a single test by name
.venv/bin/pytest tests/unit/test_state_machine.py::test_invalid_transition

# Run integration tests (requires docker infra running)
.venv/bin/pytest tests/integration/

# Lint + format
.venv/bin/ruff check app/ tests/
.venv/bin/ruff format app/ tests/

# Alembic migrations
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "description"

# Start the event consumer manually
.venv/bin/python -m app.consumer.event_consumer
```

## Architecture

**Stack:** FastAPI (async) + PostgreSQL via SQLAlchemy async + Redis Streams + Docker Compose.

**Layer separation** (critical for the gRPC bonus — both REST and gRPC handlers call `job_service.py` without duplicating logic):

```
api/v1/          → HTTP request/response only, delegates to job_service
grpc/            → gRPC handlers, same job_service calls
services/        → all business logic (job_service.py)
core/            → pipeline orchestrator, state machine, event publisher
providers/       → external provider abstractions and mocks
models/          → SQLAlchemy ORM models
consumer/        → Redis Streams consumer group (simulates downstream service)
```

**Pipeline flow:**
1. `POST /api/v1/jobs` → `job_service.create_job()` → persists job, publishes `job.created`, enqueues background task
2. Background task → `PipelineOrchestrator.run()` → calls providers sequentially per `pipeline_config.stages`
3. Each stage: publish `job.stage_started` → call provider → persist partial result → publish `job.stage_completed`
4. On completion: publish `job.completed` and set job state to `completed`
5. On any provider failure: retry with backoff (tenacity), then publish `job.failed` and move to DLQ stream

**State machine** (`core/state_machine.py`): transitions enforced via a dict — raises `InvalidTransitionError` if a transition is not allowed. Valid transitions: `pending→processing`, `processing→completed`, `processing→failed`, `pending→cancelled`, `processing→cancelled`.

**Provider abstraction** (`providers/base.py`): uses `typing.Protocol` (structural subtyping, no inheritance required). Three protocols: `ExtractionProvider`, `AnalysisProvider`, `EnrichmentProvider`. Each stage has at least two mock implementations (e.g., `FastExtractor` ~100ms, `SlowExtractor` ~2s).

**Redis Streams:**
- Main stream: `jobs:events` — all pipeline events with consumer group `gateway-consumers`
- DLQ stream: `jobs:dlq` — jobs that exhausted retries
- Events: `job.created`, `job.stage_started`, `job.stage_completed`, `job.completed`, `job.failed`, `job.cancelled`
- If Redis is unavailable: events queue in an `asyncio.Queue` and retry in background — pipeline progress is never lost

**Resiliency strategy:** retry with exponential backoff via `tenacity` on provider calls + dead letter queue for exhausted jobs. Justified in README as the most operationally useful combination (retry handles transient failures; DLQ enables manual inspection and replay).

## Key design decisions

- `pipeline_config.stages` is an ordered list — the orchestrator runs only the specified stages in that order
- Partial results are persisted to DB before each stage transition, so a failure never loses prior stage output
- Provider injection is done at app startup (dependency injection via FastAPI's `Depends`), making it easy to swap providers without touching orchestrator logic
- gRPC handlers (bonus) share `job_service.py` directly — no logic duplication
