# Document Processing Gateway

A FastAPI microservice that orchestrates document processing through a sequential provider pipeline and publishes lifecycle events to Redis Streams.

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

Run the database migrations (first time only):

```bash
docker compose exec api .venv/bin/alembic upgrade head
```

## Local Development

```bash
# Start all services
docker compose up -d

# Start only infrastructure
docker compose up postgres redis -d

# Install dependencies
uv sync --extra dev

# Apply migrations
uv run alembic upgrade head

# Start API with hot reload
uv run uvicorn app.main:app --reload

# Start event consumer (separate terminal)
uv run python -m app.consumer.event_consumer
```

## Architecture

```
                         ┌──────────────────────────────────┐
  POST /api/v1/jobs ───► │                                  │
                         │     Document Processing          │ ──► FastExtractor / SlowExtractor
  GET  /api/v1/jobs ───► │         Gateway                  │ ──► FastAnalyzer  / SlowAnalyzer
  GET  /api/v1/jobs/:id ►│        (FastAPI)                 │ ──► FastEnricher  / SlowEnricher
  DEL  /api/v1/jobs/:id ►│                                  │
                         └───────┬──────────────────────────┘
                                 │ partial results → PostgreSQL
                                 │ lifecycle events → Redis Streams
                                 ▼
                      ┌─────────────────────┐
                      │  jobs:events stream  │  (Redis Streams)
                      │  jobs:dlq stream     │
                      └─────────┬───────────┘
                                │ consumer group: gateway-consumers
                                ▼
                       ┌─────────────────┐
                       │ Event Consumer  │  (simulated downstream service)
                       └─────────────────┘
```

**Layer separation:**

| Layer                   | Responsibility                                                |
| ----------------------- | ------------------------------------------------------------- |
| `api/v1/`               | HTTP routing, request/response serialization only             |
| `services/`             | Business logic — create, get, list, cancel jobs               |
| `core/orchestrator.py`  | Sequential stage execution with retry and partial persistence |
| `core/state_machine.py` | Enforces valid state transitions                              |
| `core/events.py`        | Redis Streams publisher with in-memory fallback               |
| `providers/`            | Provider protocols and mock implementations                   |
| `consumer/`             | Redis Streams consumer group (downstream simulation)          |
| `models/`               | SQLAlchemy ORM — `Job` model                                  |

The service layer is protocol-agnostic by design — `job_service.py` contains all business logic with no HTTP coupling, so a gRPC layer (see Phase 8 / bonus) can call it directly without duplicating logic.

## API Reference

### Submit a document

```http
POST /api/v1/jobs
Content-Type: application/json

{
  "document_name": "contract.pdf",
  "document_type": "pdf",
  "document_content": "Lorem ipsum...",
  "pipeline_config": ["extraction", "analysis", "enrichment"]
}
```

`pipeline_config` controls which stages run and their order. Valid values: `extraction`, `analysis`, `enrichment`.

### Query / manage jobs

```http
GET    /api/v1/jobs?status=processing&page=1&limit=20
GET    /api/v1/jobs/{job_id}
DELETE /api/v1/jobs/{job_id}   # cancels the job
```

### Job lifecycle

```
pending ──► processing ──► completed
   │              │
   └──────────────┴──► failed
   └──────────────┴──► cancelled
```

### Events published to `jobs:events`

| Event                 | When                                     |
| --------------------- | ---------------------------------------- |
| `job.created`         | Job accepted                             |
| `job.stage_started`   | Stage begins                             |
| `job.stage_completed` | Stage succeeds (includes partial result) |
| `job.completed`       | All stages done                          |
| `job.failed`          | Unrecoverable error after retries        |
| `job.cancelled`       | Client-requested cancellation            |

Failed jobs after retry exhaustion are also written to `jobs:dlq` for manual inspection and replay.

## Running Tests

```bash
# Unit tests (no infrastructure required)
uv run pytest tests/unit/

# Integration tests (requires postgres + redis running)
docker compose up postgres redis -d
uv run pytest tests/integration/

# Full suite with coverage
uv run coverage run -m pytest
uv run coverage report
```

## Configuration

All settings are via environment variables (see `.env.example`):

| Variable                | Default | Description                                       |
| ----------------------- | ------- | ------------------------------------------------- |
| `DATABASE_URL`          | —       | Async PostgreSQL DSN (`postgresql+asyncpg://...`) |
| `REDIS_URL`             | —       | Redis DSN (`redis://...`)                         |
| `RETRY_MAX_ATTEMPTS`    | `3`     | Provider call retry limit                         |
| `RETRY_WAIT_MULTIPLIER` | `1.0`   | Exponential backoff multiplier                    |
| `RETRY_WAIT_MIN`        | `1.0`   | Min wait between retries (seconds)                |
| `RETRY_WAIT_MAX`        | `10.0`  | Max wait between retries (seconds)                |

## Technology Choices

### FastAPI

Async-first, minimal overhead, automatic OpenAPI docs, native `BackgroundTasks` for decoupling pipeline execution from request latency. Pydantic v2 for schema validation.

### PostgreSQL + SQLAlchemy async

Jobs are state-bearing entities that require ACID guarantees. Partial results are persisted after each stage so that a provider failure never rolls back completed work. SQLAlchemy's async session maps cleanly to FastAPI's dependency injection.

### Redis Streams

Chosen over Kafka (operational overhead) and RabbitMQ (lacks native consumer groups in the open-source build without plugins). Redis Streams provide:

- **Persistence** — messages survive consumer restarts.
- **Consumer groups** — multiple independent consumers can read the same stream at their own offset.
- **Acknowledgment** — `XACK` marks a message as processed; unacknowledged messages are redelivered.
- **DLQ** — a second stream (`jobs:dlq`) receives jobs that exhausted all retries, enabling manual replay without reprocessing already-completed stages.

If Redis is temporarily unavailable, events queue in an `asyncio.Queue` and a background drain loop retries every 5 seconds. Pipeline progress is never blocked or lost.

### Tenacity (retry + exponential backoff)

Transient provider errors (network blips, 5xx responses) are the most common failure mode in a provider-orchestration system. Exponential backoff with a cap avoids thundering-herd on recovery. The DLQ catches the residual cases that exhaust retries, giving operators a structured replay path rather than silent data loss.

Provider protocols use `typing.Protocol` (structural subtyping) — providers are swappable without inheritance, and the two mock variants (`Fast*` ~100ms / `Slow*` ~2s) demonstrate that the abstraction holds under different latency profiles.
