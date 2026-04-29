import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import JobCreate, JobResponse
from app.core.state_machine import InvalidTransitionError, JobStatus
from app.db.engine import get_db
from app.services.job_service import JobNotFoundError, JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_service(db: AsyncSession = Depends(get_db)) -> JobService:
    return JobService(db)


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: JobCreate,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    job = await service.create(
        document_name=body.document_name,
        document_type=body.document_type,
        document_content=body.document_content,
        pipeline_config=body.pipeline_config,
    )
    return JobResponse.model_validate(job)


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: JobStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    service: JobService = Depends(get_job_service),
) -> list[JobResponse]:
    jobs = await service.list(status=status, skip=(page - 1) * limit, limit=limit)
    return [JobResponse.model_validate(j) for j in jobs]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    try:
        job = await service.get(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JobResponse.model_validate(job)


@router.delete("/{job_id}", response_model=JobResponse)
async def cancel_job(
    job_id: uuid.UUID,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    try:
        job = await service.cancel(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return JobResponse.model_validate(job)
