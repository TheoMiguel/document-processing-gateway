# Testing Guide — Document Processing Gateway

## Prerequisites

```bash
# Start full stack
docker compose up --build -d

# Wait for health (api, postgres, redis ready)
docker compose ps

# Or run infra only + local API
docker compose up postgres redis -d
uv run uvicorn app.main:app --reload
```

Verify the API is up:

```bash
curl -s http://localhost:8000/health
# {"status":"ok"}
```

Run the existing automated test suites:

```bash
# Unit tests only (no infra required)
uv run pytest tests/unit/ -v

# Integration tests (requires docker infra)
uv run pytest tests/integration/ -v

# All tests with coverage
uv run pytest --cov=app --cov-report=term-missing
```

---

## Scenario 1 — Full Pipeline (Happy Path)

Submit a job with all three stages and watch it go through `pending → processing → completed`.

```bash
curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "contract.pdf",
    "document_type": "contract",
    "document_content": "This is a legal contract agreement between two parties for the sale of goods and services.",
    "pipeline_config": ["extraction", "analysis", "enrichment"]
  }' | python3 -m json.tool
```

**Expected response (201):**

```json
{
  "id": "<uuid>",
  "status": "pending",
  "document_name": "contract.pdf",
  "document_type": "contract",
  "pipeline_config": ["extraction", "analysis", "enrichment"],
  "partial_results": null,
  "error_message": null,
  "created_at": "...",
  "updated_at": "..."
}
```

Poll until completed:

```bash
JOB_ID=<uuid from above>

# Poll every second until status is not pending/processing
watch -n 1 "curl -s http://localhost:8000/api/v1/jobs/$JOB_ID | python3 -m json.tool"
```

**Expected final state:**

```json
{
  "status": "completed",
  "partial_results": {
    "extraction": {
      "word_count": 17,
      "document_type": "contract",
      "extracted_text": "..."
    },
    "analysis": {
      "sentiment": "neutral",
      "complexity": "low",
      "key_topics": [...]
    },
    "enrichment": {
      "category": "...",
      "confidence": 0.0-1.0,
      "metadata": {...}
    }
  }
}
```

**Redis events to verify:**

```bash
docker exec -it inceptia-redis-1 redis-cli XRANGE jobs:events - +
```

You should see entries for: `job.created`, `job.stage_started` (×3), `job.stage_completed` (×3), `job.completed`.

---

## Scenario 2 — Partial Pipeline (Single Stage)

```bash
curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "invoice.txt",
    "document_type": "invoice",
    "document_content": "Invoice #1234 for services rendered.",
    "pipeline_config": ["extraction"]
  }' | python3 -m json.tool
```

**Expected:** job completes with only `extraction` key inside `partial_results`. No `analysis` or `enrichment` keys.

Redis events: `job.created`, `job.stage_started`, `job.stage_completed`, `job.completed` — exactly 4 entries for this job (filter by `job_id` field in stream data).

---

## Scenario 3 — Pipeline Stage Order Enforcement

The orchestrator enforces the canonical order: `extraction → analysis → enrichment`, regardless of input order.

```bash
curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "report.txt",
    "document_type": "report",
    "document_content": "Annual report with detailed financial analysis.",
    "pipeline_config": ["enrichment", "extraction", "analysis"]
  }' | python3 -m json.tool
```

**Expected:** job completes successfully; stages execute in the canonical order even though the config listed them out of order. `partial_results` has all three keys populated in execution order.

---

## Scenario 4 — List Jobs and Filter by Status

```bash
# Create a few jobs
for i in 1 2 3; do
  curl -s -X POST http://localhost:8000/api/v1/jobs \
    -H "Content-Type: application/json" \
    -d "{\"document_name\": \"doc$i.txt\", \"document_type\": \"report\", \"document_content\": \"Content $i\", \"pipeline_config\": [\"extraction\"]}" \
    | python3 -m json.tool
done

# List all jobs
curl -s "http://localhost:8000/api/v1/jobs" | python3 -m json.tool

# Filter by status
curl -s "http://localhost:8000/api/v1/jobs?status=completed" | python3 -m json.tool
curl -s "http://localhost:8000/api/v1/jobs?status=pending" | python3 -m json.tool

# Pagination
curl -s "http://localhost:8000/api/v1/jobs?limit=2&offset=0" | python3 -m json.tool
curl -s "http://localhost:8000/api/v1/jobs?limit=2&offset=2" | python3 -m json.tool
```

**Expected:** array of job objects matching the filter. Pagination slices the result correctly.

---

## Scenario 5 — Cancel a Pending Job

Submit a job with a slow pipeline, then immediately cancel it before it finishes.

```bash
JOB_ID=$(curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "slow.txt",
    "document_type": "report",
    "document_content": "Cancellation test",
    "pipeline_config": ["extraction", "analysis", "enrichment"]
  }' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "Job ID: $JOB_ID"

# Cancel immediately
curl -s -X DELETE "http://localhost:8000/api/v1/jobs/$JOB_ID" | python3 -m json.tool
```

**Expected (204 or 200):** job transitions to `cancelled`. A `job.cancelled` event is published to Redis.

Verify:

```bash
curl -s "http://localhost:8000/api/v1/jobs/$JOB_ID" | python3 -m json.tool
# "status": "cancelled"
```

---

## Scenario 6 — Cancel a Completed Job (Conflict)

```bash
# Create and wait for completion
JOB_ID=$(curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "done.txt",
    "document_type": "report",
    "document_content": "Already done",
    "pipeline_config": ["extraction"]
  }' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

sleep 3  # wait for pipeline to complete

curl -s -X DELETE "http://localhost:8000/api/v1/jobs/$JOB_ID" | python3 -m json.tool
```

**Expected (409 Conflict):**

```json
{"detail": "Cannot cancel job in completed state"}
```

---

## Scenario 7 — Job Not Found

```bash
curl -s "http://localhost:8000/api/v1/jobs/00000000-0000-0000-0000-000000000000" | python3 -m json.tool

curl -s -X DELETE "http://localhost:8000/api/v1/jobs/00000000-0000-0000-0000-000000000000" | python3 -m json.tool
```

**Expected (404):**

```json
{"detail": "Job not found"}
```

---

## Scenario 8 — Input Validation Errors

**Empty pipeline_config:**

```bash
curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "test.txt",
    "document_type": "report",
    "document_content": "content",
    "pipeline_config": []
  }' | python3 -m json.tool
```

**Expected (422):**

```json
{
  "detail": [{"msg": "Value error, pipeline_config must contain at least one stage", ...}]
}
```

**Invalid stage name:**

```bash
curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "test.txt",
    "document_type": "report",
    "document_content": "content",
    "pipeline_config": ["nonexistent_stage"]
  }' | python3 -m json.tool
```

**Expected (422):** validation error listing valid stage literals.

**Missing required fields:**

```bash
curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"document_name": "test.txt"}' | python3 -m json.tool
```

**Expected (422):** missing field errors for `document_type`, `document_content`, `pipeline_config`.

---

## Scenario 9 — Redis Unavailable (Fallback Queue)

Test that the pipeline keeps running and events drain to Redis once it recovers.

```bash
# Stop redis
docker compose stop redis

# Submit a job
curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "offline.txt",
    "document_type": "report",
    "document_content": "Redis is down but we still process",
    "pipeline_config": ["extraction"]
  }' | python3 -m json.tool

# Check API logs — should show fallback queue messages
docker logs inceptia-api-1 --tail 30
```

**Expected logs:**

```
Failed to publish to Redis, falling back to local queue
Event queued locally: job.created ...
```

The job still moves through the pipeline via the database.

```bash
# Bring Redis back
docker compose start redis

# Wait ~5s for drain loop, then check stream
sleep 6
docker exec -it inceptia-redis-1 redis-cli XRANGE jobs:events - +
```

**Expected:** events that were queued locally are now visible in the Redis stream after Redis recovers.

---

## Scenario 10 — Provider Failure and DLQ

Simulate a provider failure by temporarily patching a provider to always raise an exception. Since this requires code modification, use the following unit-test approach:

```bash
uv run pytest tests/unit/test_orchestrator.py -v -k "fail"
```

**Alternatively, add a failing provider via the test fixture and run:**

```bash
uv run pytest tests/unit/test_orchestrator.py::test_provider_failure -v -s
```

**Expected log output (from unit test):**

```
Job <id>: stage extraction failed — <error message>
Job <id>: all retries exhausted, publishing to DLQ
```

**Verify DLQ stream (integration context):**

```bash
docker exec -it inceptia-redis-1 redis-cli XRANGE jobs:dlq - +
```

Failed jobs have their `error_message` set and `status = failed`.

---

## Scenario 11 — Partial Results Accumulate Before Completion

Submit a multi-stage job and poll for partial results between stages.

```bash
JOB_ID=$(curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "partial.txt",
    "document_type": "report",
    "document_content": "This document has many words to trigger medium complexity analysis in the pipeline.",
    "pipeline_config": ["extraction", "analysis", "enrichment"]
  }' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Poll every 0.5s and print partial_results as they appear
for i in $(seq 1 20); do
  curl -s "http://localhost:8000/api/v1/jobs/$JOB_ID" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d['status'], d['partial_results'])"
  sleep 0.5
done
```

**Expected progression:**

```
pending   None
processing {'extraction': {...}}
processing {'extraction': {...}, 'analysis': {...}}
completed  {'extraction': {...}, 'analysis': {...}, 'enrichment': {...}}
```

---

## Scenario 12 — gRPC Interface

Install `grpcurl` if needed: `brew install grpcurl` / `apt install grpcurl`.

```bash
# List available services
grpcurl -plaintext localhost:50051 list

# Submit a document via gRPC
grpcurl -plaintext -d '{
  "document_name": "grpc_doc.pdf",
  "document_type": "contract",
  "document_content": "gRPC submitted document content here",
  "pipeline_config": ["extraction", "analysis"]
}' localhost:50051 gateway.DocumentGateway/SubmitDocument

# Get job status via gRPC (use the job_id from above)
grpcurl -plaintext -d '{"job_id": "<uuid>"}' \
  localhost:50051 gateway.DocumentGateway/GetJobStatus
```

**Expected SubmitDocument response:**

```json
{
  "jobId": "<uuid>",
  "status": "JOB_STATUS_PENDING",
  "documentName": "grpc_doc.pdf"
}
```

**Expected GetJobStatus after completion:**

```json
{
  "jobId": "<uuid>",
  "status": "JOB_STATUS_COMPLETED",
  ...
}
```

**Error case — invalid UUID:**

```bash
grpcurl -plaintext -d '{"job_id": "not-a-uuid"}' \
  localhost:50051 gateway.DocumentGateway/GetJobStatus
```

**Expected:** gRPC status `NOT_FOUND` or `INVALID_ARGUMENT`.

---

## Scenario 13 — Event Consumer Logs

The consumer service reads from the `jobs:events` stream and logs each event.

```bash
# Watch consumer logs in real time
docker logs -f inceptia-consumer-1

# In another terminal, submit a job
curl -s -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "watched.txt",
    "document_type": "invoice",
    "document_content": "Consumer log test",
    "pipeline_config": ["extraction"]
  }'
```

**Expected consumer output:**

```
Received event: job.created — job_id=<uuid> ...
Received event: job.stage_started — stage=extraction ...
Received event: job.stage_completed — stage=extraction ...
Received event: job.completed — job_id=<uuid> ...
```

---

## Scenario 14 — Concurrent Job Submissions

```bash
# Submit 10 jobs concurrently
for i in $(seq 1 10); do
  curl -s -X POST http://localhost:8000/api/v1/jobs \
    -H "Content-Type: application/json" \
    -d "{\"document_name\": \"concurrent$i.txt\", \"document_type\": \"report\", \"document_content\": \"Concurrent job $i content\", \"pipeline_config\": [\"extraction\", \"analysis\"]}" &
done
wait

# Check all completed without errors
curl -s "http://localhost:8000/api/v1/jobs?status=completed" | python3 -c \
  "import sys,json; jobs=json.load(sys.stdin); print(f'Completed: {len(jobs)}')"

curl -s "http://localhost:8000/api/v1/jobs?status=failed" | python3 -c \
  "import sys,json; jobs=json.load(sys.stdin); print(f'Failed: {len(jobs)}')"
```

**Expected:** all 10 jobs complete successfully, 0 failed.

---

## Script: `scripts/smoke_test.sh`

A quick end-to-end smoke test that exercises the main happy path and common error cases:

```bash
bash scripts/smoke_test.sh
```

See `scripts/smoke_test.sh` for source.

---

## Interpreting Logs

```bash
# API logs
docker logs inceptia-api-1 --tail 50 -f

# Consumer logs
docker logs inceptia-consumer-1 --tail 50 -f

# All logs together
docker compose logs -f
```

Key log lines to look for:

| Log line | Meaning |
|---|---|
| `Published event job.created` | Event hit Redis stream |
| `Failed to publish to Redis, falling back` | Redis unreachable, local queue active |
| `Draining X events to Redis` | Drain loop flushing the local queue |
| `Stage extraction completed` | Provider finished |
| `Retry attempt N for stage` | Tenacity retrying a provider call |
| `Job <id> moved to DLQ` | All retries exhausted |
| `Consumer: received event` | Consumer successfully read from stream |

---

## Redis Inspection Commands

```bash
# List all events in the main stream
docker exec -it inceptia-redis-1 redis-cli XRANGE jobs:events - +

# Count events
docker exec -it inceptia-redis-1 redis-cli XLEN jobs:events

# Inspect DLQ
docker exec -it inceptia-redis-1 redis-cli XRANGE jobs:dlq - +

# Consumer group info
docker exec -it inceptia-redis-1 redis-cli XINFO GROUPS jobs:events
docker exec -it inceptia-redis-1 redis-cli XINFO CONSUMERS jobs:events gateway-consumers

# Pending (unacknowledged) messages
docker exec -it inceptia-redis-1 redis-cli XPENDING jobs:events gateway-consumers - + 10
```

---

## Database Inspection

```bash
# Connect to postgres
docker exec -it inceptia-postgres-1 psql -U postgres -d postgres

-- List all jobs
SELECT id, status, document_name, created_at FROM jobs ORDER BY created_at DESC;

-- Jobs by status
SELECT status, count(*) FROM jobs GROUP BY status;

-- Inspect partial results for a specific job
SELECT id, status, partial_results, error_message FROM jobs WHERE id = '<uuid>';

-- Check for failed jobs
SELECT id, error_message, updated_at FROM jobs WHERE status = 'failed';
```
