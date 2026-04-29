import asyncio
import json
import logging
import os
import socket

import redis.asyncio as aioredis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STREAM = "jobs:events"
GROUP = "gateway-consumers"
CONSUMER = f"consumer-{socket.gethostname()}"


async def main() -> None:
    redis_url = os.environ["REDIS_URL"]
    client: aioredis.Redis = aioredis.from_url(redis_url, decode_responses=True)

    try:
        await client.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise

    logger.info("Consumer %s started, reading from %s/%s", CONSUMER, STREAM, GROUP)

    while True:
        results = await client.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=10, block=5000)
        if not results:
            continue
        for _stream_name, messages in results:
            for msg_id, fields in messages:
                payload = json.loads(fields.get("payload", "{}"))
                logger.info(
                    "[%s] job_id=%s payload=%s",
                    fields.get("event_type"),
                    fields.get("job_id"),
                    payload,
                )
                await client.xack(STREAM, GROUP, msg_id)


if __name__ == "__main__":
    asyncio.run(main())
