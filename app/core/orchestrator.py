import uuid
from datetime import datetime, timezone
from typing import Any

from tenacity import AsyncRetrying, RetryError, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.events import EventPublisher
from app.core.state_machine import InvalidTransitionError, JobStatus, transition
from app.db.engine import AsyncSessionLocal
from app.models.job import Job
from app.providers.base import AnalysisProvider, EnrichmentProvider, ExtractionProvider


def _retry_kwargs() -> dict:
    return dict(
        stop=stop_after_attempt(settings.retry_max_attempts),
        wait=wait_exponential(
            multiplier=settings.retry_wait_multiplier,
            min=settings.retry_wait_min,
            max=settings.retry_wait_max,
        ),
        reraise=True,
    )


STAGE_ORDER = ["extraction", "analysis", "enrichment"]


class PipelineOrchestrator:
    def __init__(
        self,
        extraction: ExtractionProvider,
        analysis: AnalysisProvider,
        enrichment: EnrichmentProvider,
        publisher: EventPublisher,
    ) -> None:
        self.extraction = extraction
        self.analysis = analysis
        self.enrichment = enrichment
        self.publisher = publisher

    async def run(self, job_id: uuid.UUID) -> None:
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_id)
            if job is None:
                return

            unknown = set(job.pipeline_config) - set(STAGE_ORDER)
            if unknown:
                job.status = transition(job.status, JobStatus.failed)
                job.error_message = f"Unknown stages: {sorted(unknown)}"
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
                await self.publisher.publish("job.failed", job.id, {"error": job.error_message})
                return

            ordered_stages = [s for s in STAGE_ORDER if s in job.pipeline_config]

            job.status = transition(job.status, JobStatus.processing)
            job.updated_at = datetime.now(timezone.utc)
            await db.commit()

            partial: dict[str, Any] = {}
            try:
                for stage in ordered_stages:
                    await self.publisher.publish("job.stage_started", job.id, {"stage": stage})
                    async for attempt in AsyncRetrying(**_retry_kwargs()):
                        with attempt:
                            if stage == "extraction":
                                partial["extraction"] = await self.extraction.extract(
                                    job.document_content, job.document_type
                                )
                            elif stage == "analysis":
                                partial["analysis"] = await self.analysis.analyze(
                                    partial.get("extraction", {})
                                )
                            elif stage == "enrichment":
                                partial["enrichment"] = await self.enrichment.enrich(
                                    partial.get("extraction", {}), partial.get("analysis", {})
                                )
                    job.partial_results = dict(partial)
                    job.updated_at = datetime.now(timezone.utc)
                    await db.commit()
                    await self.publisher.publish(
                        "job.stage_completed",
                        job.id,
                        {"stage": stage, "result": partial[stage]},
                    )

                job.status = transition(job.status, JobStatus.completed)
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
                await self.publisher.publish("job.completed", job.id, {})

            except InvalidTransitionError:
                raise
            except RetryError as exc:
                cause = str(exc.last_attempt.exception())
                job.status = transition(job.status, JobStatus.failed)
                job.error_message = cause
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
                await self.publisher.publish("job.failed", job.id, {"error": cause})
                await self.publisher.publish_dlq(job.id, {"error": cause, "job_id": str(job.id)})
            except Exception as exc:
                job.status = transition(job.status, JobStatus.failed)
                job.error_message = str(exc)
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
                await self.publisher.publish("job.failed", job.id, {"error": str(exc)})
