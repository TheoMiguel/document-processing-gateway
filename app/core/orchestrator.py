import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.state_machine import InvalidTransitionError, JobStatus, transition
from app.db.engine import AsyncSessionLocal
from app.models.job import Job
from app.providers.base import AnalysisProvider, EnrichmentProvider, ExtractionProvider

STAGE_ORDER = ["extraction", "analysis", "enrichment"]


class PipelineOrchestrator:
    def __init__(
        self,
        extraction: ExtractionProvider,
        analysis: AnalysisProvider,
        enrichment: EnrichmentProvider,
    ) -> None:
        self.extraction = extraction
        self.analysis = analysis
        self.enrichment = enrichment

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
                return

            ordered_stages = [s for s in STAGE_ORDER if s in job.pipeline_config]

            job.status = transition(job.status, JobStatus.processing)
            job.updated_at = datetime.now(timezone.utc)
            await db.commit()

            partial: dict[str, Any] = {}
            try:
                for stage in ordered_stages:
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

                job.status = transition(job.status, JobStatus.completed)
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()

            except InvalidTransitionError:
                raise
            except Exception as exc:
                job.status = transition(job.status, JobStatus.failed)
                job.error_message = str(exc)
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
