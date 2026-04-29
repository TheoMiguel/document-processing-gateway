import asyncio
import json
import uuid
from datetime import timezone

import grpc
import grpc.aio
from google.protobuf import struct_pb2, timestamp_pb2

from app.core.events import EventPublisher
from app.core.orchestrator import PipelineOrchestrator
from app.core.state_machine import JobStatus
from app.db.engine import AsyncSessionLocal
from app.grpc.generated import gateway_pb2, gateway_pb2_grpc
from app.models.job import Job
from app.services.job_service import JobNotFoundError, JobService

_STATUS_MAP = {
    JobStatus.pending: gateway_pb2.JOB_STATUS_PENDING,
    JobStatus.processing: gateway_pb2.JOB_STATUS_PROCESSING,
    JobStatus.completed: gateway_pb2.JOB_STATUS_COMPLETED,
    JobStatus.failed: gateway_pb2.JOB_STATUS_FAILED,
    JobStatus.cancelled: gateway_pb2.JOB_STATUS_CANCELLED,
}


def _job_to_proto(job: Job) -> gateway_pb2.JobMessage:
    created_ts = timestamp_pb2.Timestamp()
    dt_created = job.created_at
    if dt_created.tzinfo is None:
        dt_created = dt_created.replace(tzinfo=timezone.utc)
    created_ts.FromDatetime(dt_created)

    updated_ts = timestamp_pb2.Timestamp()
    dt_updated = job.updated_at
    if dt_updated.tzinfo is None:
        dt_updated = dt_updated.replace(tzinfo=timezone.utc)
    updated_ts.FromDatetime(dt_updated)

    partial = struct_pb2.Struct()
    if job.partial_results:
        safe = json.loads(json.dumps(job.partial_results, default=str))
        partial.update(safe)

    return gateway_pb2.JobMessage(
        id=str(job.id),
        status=_STATUS_MAP[job.status],
        document_name=job.document_name,
        document_type=job.document_type,
        pipeline_config=list(job.pipeline_config),
        partial_results=partial,
        error_message=job.error_message or "",
        created_at=created_ts,
        updated_at=updated_ts,
    )


class DocumentGatewayServicer(gateway_pb2_grpc.DocumentGatewayServicer):
    def __init__(self, publisher: EventPublisher, orchestrator: PipelineOrchestrator) -> None:
        self._publisher = publisher
        self._orchestrator = orchestrator

    async def SubmitDocument(
        self,
        request: gateway_pb2.SubmitDocumentRequest,
        context: grpc.aio.ServicerContext,
    ) -> gateway_pb2.SubmitDocumentResponse:
        if not request.pipeline_config:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "pipeline_config must contain at least one stage",
            )
            return gateway_pb2.SubmitDocumentResponse()

        async with AsyncSessionLocal() as db:
            service = JobService(db, self._publisher)
            job = await service.create(
                document_name=request.document_name,
                document_type=request.document_type,
                document_content=request.document_content,
                pipeline_config=list(request.pipeline_config),
            )

        asyncio.create_task(self._orchestrator.run(job.id))
        return gateway_pb2.SubmitDocumentResponse(job=_job_to_proto(job))

    async def GetJobStatus(
        self,
        request: gateway_pb2.GetJobStatusRequest,
        context: grpc.aio.ServicerContext,
    ) -> gateway_pb2.GetJobStatusResponse:
        try:
            job_id = uuid.UUID(request.job_id)
        except ValueError:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"'{request.job_id}' is not a valid UUID",
            )
            return gateway_pb2.GetJobStatusResponse()

        async with AsyncSessionLocal() as db:
            service = JobService(db, self._publisher)
            try:
                job = await service.get(job_id)
            except JobNotFoundError:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Job {request.job_id} not found",
                )
                return gateway_pb2.GetJobStatusResponse()

        return gateway_pb2.GetJobStatusResponse(job=_job_to_proto(job))
