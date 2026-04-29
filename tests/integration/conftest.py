import asyncio
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.events import STREAM, EventPublisher
from app.core.orchestrator import PipelineOrchestrator
from app.db.engine import AsyncSessionLocal, engine
from app.main import app
from app.providers.analysis import FastAnalyzer
from app.providers.enrichment import FastEnricher
from app.providers.extraction import FastExtractor

PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture(scope="session", autouse=True)
def run_migrations():
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd=PROJECT_ROOT,
    )


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    # Dispose stale connections from the previous test's event loop before reusing the pool
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(text("TRUNCATE TABLE jobs CASCADE"))
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def clean_redis():
    r = aioredis.from_url(settings.redis_url)
    await r.delete(STREAM)
    await r.aclose()


@pytest_asyncio.fixture
async def client():
    # ASGITransport does not trigger ASGI lifespan, so we set up app.state manually
    publisher = EventPublisher(settings.redis_url)
    await publisher.connect()
    drain_task = asyncio.create_task(publisher.drain_loop())
    app.state.publisher = publisher
    app.state.orchestrator = PipelineOrchestrator(
        extraction=FastExtractor(),
        analysis=FastAnalyzer(),
        enrichment=FastEnricher(),
        publisher=publisher,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    drain_task.cancel()
    try:
        await drain_task
    except asyncio.CancelledError:
        pass
    await publisher.close()


@pytest_asyncio.fixture
async def redis_client():
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    yield r
    await r.aclose()
