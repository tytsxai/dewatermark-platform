from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

MediaType = Literal["video", "image"]
ProviderName = Literal["auto", "comfy_diffueraser", "local_fallback"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]
CallbackDeliveryStatus = Literal["pending", "delivering", "succeeded", "failed"]


class JobCreate(BaseModel):
    tenant_id: str
    media_type: MediaType
    provider_requested: ProviderName
    fallback_chain_json: str
    idempotency_key: str | None = None
    input_path: str
    input_signature: str | None = None
    callback_url: str | None = None
    callback_secret: str | None = None
    priority: int = 0


class JobRecord(BaseModel):
    job_id: str
    tenant_id: str
    media_type: MediaType
    status: JobStatus
    provider_requested: ProviderName
    provider_selected: str | None = None
    fallback_chain_json: str
    idempotency_key: str | None = None
    input_path: str
    input_signature: str | None = None
    output_path: str | None = None
    callback_url: str | None = None
    callback_secret: str | None = None
    priority: int = 0
    attempt_count: int = 0
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    claimed_at: datetime | None = None
    lock_owner: str | None = None


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    media_type: MediaType
    provider_requested: ProviderName
    provider_selected: str | None = None
    output_path: str | None = None
    attempt_count: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, job: JobRecord) -> "JobResponse":
        return cls(
            job_id=job.job_id,
            status=job.status,
            media_type=job.media_type,
            provider_requested=job.provider_requested,
            provider_selected=job.provider_selected,
            output_path=job.output_path,
            attempt_count=job.attempt_count,
            error_code=job.error_code,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    page: int = 1
    page_size: int = 50
    has_more: bool = False


class JobSubmitResponse(BaseModel):
    job_id: str
    status: JobStatus
    provider_requested: ProviderName
    created_at: datetime


class ProviderProbeResult(BaseModel):
    name: str
    installed: bool
    runnable: bool
    message: str = Field(default="")
    details: dict[str, Any] | None = None


class JobResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    output_path: str | None = None
    download_url: str | None = None


class CancelJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    updated_at: datetime


class CallbackPayload(BaseModel):
    job_id: str
    status: JobStatus
    provider: str | None = None
    output_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class CallbackOutboxRecord(BaseModel):
    id: int
    job_id: str
    tenant_id: str
    callback_url: str
    callback_secret: str | None = None
    payload_json: str
    status: CallbackDeliveryStatus
    attempt_count: int = 0
    max_attempts: int
    next_attempt_at: datetime
    last_error: str | None = None
    last_response_code: int | None = None
    last_response_body: str | None = None
    claimed_at: datetime | None = None
    lock_owner: str | None = None
    created_at: datetime
    updated_at: datetime


class RunMetadataRecord(BaseModel):
    """运行元数据记录"""
    id: int
    job_id: str
    workflow_name: str | None = None
    quality_profile: str | None = None
    steps: int | None = None
    subvideo_length: int | None = None
    neighbor_length: int | None = None
    mask_dilation_iter: int | None = None
    device: str | None = None
    seed: int | None = None
    scene_type: str | None = None
    confidence_level: str | None = None
    created_at: datetime
