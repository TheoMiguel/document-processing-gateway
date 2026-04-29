import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.jobs import router as jobs_router
from app.core.config import settings
from app.core.events import EventPublisher
from app.core.orchestrator import PipelineOrchestrator
from app.providers.analysis import FastAnalyzer
from app.providers.enrichment import FastEnricher
from app.providers.extraction import FastExtractor


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    yield
    drain_task.cancel()
    await publisher.close()


app = FastAPI(title="Document Processing Gateway", lifespan=lifespan)

app.include_router(jobs_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
