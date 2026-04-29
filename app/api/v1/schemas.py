import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.state_machine import JobStatus

Stage = Literal["extraction", "analysis", "enrichment"]


class JobCreate(BaseModel):
    document_name: str
    document_type: str
    document_content: str
    pipeline_config: list[Stage]

    @field_validator("pipeline_config")
    @classmethod
    def pipeline_not_empty(cls, v: list[Stage]) -> list[Stage]:
        if not v:
            raise ValueError("pipeline_config must contain at least one stage")
        return v


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
