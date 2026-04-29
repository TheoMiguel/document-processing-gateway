# Roadmap

## Phase 0 — Repo scaffolding

- [x] Project structure: directories, `__init__.py` files, `app/main.py` FastAPI hello world
- [x] Dependency management: `pyproject.toml` with `uv` (or `requirements.txt` split dev/prod)
- [x] Linting + formatting: `ruff` (lint + format), config in `pyproject.toml`
- [x] Pre-commit hooks: ruff, trailing whitespace, end-of-file fixer
- [x] Test setup: `pytest` + `pytest-asyncio`, `httpx` for async client, `coverage` config
- [x] CI: GitHub Actions workflow — lint, type-check, unit tests on every push/PR
- [x] Docker: `Dockerfile` for the API, `docker-compose.yml` with `api`, `postgres`, `redis`
- [x] Alembic: migration setup wired to SQLAlchemy async engine
- [x] `.env.example` + settings model (`pydantic-settings`)

## Phase 1 — Core domain

- [x] SQLAlchemy `Job` model
- [x] State machine with valid transitions and `InvalidTransitionError`
- [x] `JobService`: create, get, list (with status filter), cancel
- [x] Alembic initial migration

## Phase 2 — API layer

- [x] `POST /api/v1/jobs`
- [x] `GET /api/v1/jobs`
- [x] `GET /api/v1/jobs/{job_id}`
- [x] `DELETE /api/v1/jobs/{job_id}`
- [x] Pydantic request/response schemas
- [x] Error handling (404, 409 for invalid transitions, 422)

## Phase 3 — Providers + pipeline

- [x] `ExtractionProvider`, `AnalysisProvider`, `EnrichmentProvider` protocols
- [x] Two mock implementations per provider (fast ~100ms / slow ~2s)
- [x] `PipelineOrchestrator`: sequential stage execution, partial result persistence
- [x] Wire orchestrator as a FastAPI background task on job creation

## Phase 4 — Event streaming

- [x] Redis Streams publisher (`core/events.py`)
- [x] Consumer group setup and `event_consumer.py`
- [x] Publish all 6 required events throughout the pipeline
- [x] Fallback queue for when Redis is unavailable

## Phase 5 — Resiliency

- [x] Retry with exponential backoff on provider calls (`tenacity`)
- [x] Dead letter queue stream (`jobs:dlq`) for exhausted jobs
- [x] Broker-down handling (in-memory queue + background retry)

## Phase 6 — Testing

- [x] Unit: state machine transitions
- [x] Unit: `JobService` (mocked DB)
- [x] Unit: provider mocks
- [x] Unit: pipeline orchestrator (mocked providers + mocked event publisher)
- [x] Integration: full flow — create job → pipeline → events → completion

## Phase 7 — Docs + polish

- [x] `README.md`: setup instructions, architecture diagram, technology choices justified
- [x] Review error messages and HTTP status codes
- [x] Final pass on Docker Compose (healthchecks, restart policies)

## Phase 8 — Bonus: gRPC

- [x] `gateway.proto`: `SubmitDocument` and `GetJobStatus` RPCs
- [x] gRPC server setup
- [x] Handlers in `grpc/gateway.py` calling `job_service.py` directly
