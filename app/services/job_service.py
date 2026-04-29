import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state_machine import JobStatus, transition
from app.models.job import Job


class JobNotFoundError(Exception):
    pass


class JobService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        document_name: str,
        document_type: str,
        document_content: str,
        pipeline_config: list[str],
    ) -> Job:
        job = Job(
            document_name=document_name,
            document_type=document_type,
            document_content=document_content,
            pipeline_config=pipeline_config,
            status=JobStatus.pending,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get(self, job_id: uuid.UUID) -> Job:
        result = await self.db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    async def list(
        self,
        status: JobStatus | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Job]:
        stmt = select(Job)
        if status is not None:
            stmt = stmt.where(Job.status == status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def cancel(self, job_id: uuid.UUID) -> Job:
        job = await self.get(job_id)
        job.status = transition(job.status, JobStatus.cancelled)
        job.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(job)
        return job
