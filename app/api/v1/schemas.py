import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.state_machine import JobStatus


class JobCreate(BaseModel):
    document_name: str
    document_type: str
    document_content: str
    pipeline_config: list[str]


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: JobStatus
    document_name: str
    document_type: str
    pipeline_config: list[str]
    partial_results: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
