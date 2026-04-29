import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

STREAM = "jobs:events"
DLQ_STREAM = "jobs:dlq"


class EventPublisher:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: aioredis.Redis | None = None
        self._fallback: asyncio.Queue[dict] = asyncio.Queue()

    async def connect(self) -> None:
        self._client = aioredis.from_url(self._redis_url, decode_responses=False)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def publish(self, event_type: str, job_id: uuid.UUID, payload: dict) -> None:
        fields = {
            "event_type": event_type,
            "job_id": str(job_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": json.dumps(payload),
        }
        try:
            assert self._client is not None
            await self._client.xadd(STREAM, fields)
        except Exception:
            logger.warning("Redis unavailable, queuing event %s for job %s", event_type, job_id)
            await self._fallback.put(fields)

    async def publish_dlq(self, job_id: uuid.UUID, payload: dict) -> None:
        fields = {
            "job_id": str(job_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": json.dumps(payload),
        }
        try:
            assert self._client is not None
            await self._client.xadd(DLQ_STREAM, fields)
        except Exception:
            logger.error("Failed to publish to DLQ for job %s: %s", job_id, payload)

    async def drain_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            if self._fallback.empty():
                continue
            pending: list[dict] = []
            while not self._fallback.empty():
                pending.append(self._fallback.get_nowait())
            failed: list[dict] = []
            for fields in pending:
                try:
                    assert self._client is not None
                    await self._client.xadd(STREAM, fields)
                except Exception:
                    failed.append(fields)
            for fields in failed:
                await self._fallback.put(fields)
            if pending and not failed:
                logger.info("Flushed %d queued events to Redis", len(pending))
