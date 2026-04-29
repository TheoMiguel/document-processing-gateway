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

- [ ] `ExtractionProvider`, `AnalysisProvider`, `EnrichmentProvider` protocols
- [ ] Two mock implementations per provider (fast ~100ms / slow ~2s)
- [ ] `PipelineOrchestrator`: sequential stage execution, partial result persistence
- [ ] Wire orchestrator as a FastAPI background task on job creation

## Phase 4 — Event streaming

- [ ] Redis Streams publisher (`core/events.py`)
- [ ] Consumer group setup and `event_consumer.py`
- [ ] Publish all 6 required events throughout the pipeline
- [ ] Fallback queue for when Redis is unavailable

## Phase 5 — Resiliency

- [ ] Retry with exponential backoff on provider calls (`tenacity`)
- [ ] Dead letter queue stream (`jobs:dlq`) for exhausted jobs
- [ ] Broker-down handling (in-memory queue + background retry)

## Phase 6 — Testing

- [ ] Unit: state machine transitions
- [ ] Unit: `JobService` (mocked DB)
- [ ] Unit: provider mocks
- [ ] Unit: pipeline orchestrator (mocked providers + mocked event publisher)
- [ ] Integration: full flow — create job → pipeline → events → completion

## Phase 7 — Docs + polish

- [ ] `README.md`: setup instructions, architecture diagram, technology choices justified
- [ ] Review error messages and HTTP status codes
- [ ] Final pass on Docker Compose (healthchecks, restart policies)

## Phase 8 — Bonus: gRPC

- [ ] `gateway.proto`: `SubmitDocument` and `GetJobStatus` RPCs
- [ ] gRPC server setup
- [ ] Handlers in `grpc/gateway.py` calling `job_service.py` directly
